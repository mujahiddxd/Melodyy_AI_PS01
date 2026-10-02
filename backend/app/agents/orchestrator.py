"""Agent orchestrator: plain Python, no framework. One customer message in -> bot reply + order update out.

  Intake -> Parser -> (unit normalizer) -> Matcher -> Inventory -> [save order] -> Clarifier -> Messaging

Everything the LLM produces is validated before it is used. If any LLM step fails, the request's transaction is
rolled back (nothing is written to the order) and the customer gets a safe "dobara bhejiye" message.
Inventory is never modified here; it is deducted only at confirmation (Stage 4).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import answer as answer_agent
from app.agents import availability as availability_agent
from app.agents.base import RunCtx
from app.agents.clarifier import run_clarifier
from app.agents.intake import IntakeResult, run_intake
from app.agents.inventory import run_inventory
from app.agents.matcher import run_matcher
from app.agents.messaging import run_messaging
from app.agents.parser import TooManyItems, run_parser
from app.agents.types import ItemPlan
from app.llm.client import LLMError
from app.models import AgentRun, Clarification, Conversation, Message, Order, OrderItem, Product, Shop
from app.services import language as lang_svc
from app.services import orders as orders_svc
from app.services.matcher import CatalogIndex, match
from app.services.unit_normalizer import extract_quantity, normalize

log = logging.getLogger("hod.orchestrator")

AVAILABILITY_INTENTS = {"availability_query", "status_query"}
UNSUPPORTED_INTENTS = {"confirm", "cancel", "remove_items", "change_quantity", "repeat_last_order", "status_query"}


@dataclass
class ChatResult:
    messages: list[Message]
    order: Order | None
    runs: list[AgentRun]
    failed: bool = False  # an LLM step failed: the safe failure message was stored, the order is untouched


@dataclass
class _Turn:
    ctx: RunCtx
    conv: Conversation
    shop: Shop
    catalog: list[Product]
    index: CatalogIndex
    order: Order | None
    customer_text: str
    bot: Message | None = None
    products: dict[int, Product] = field(default_factory=dict)


def _load_runs(db: Session, ids: list[int]) -> list[AgentRun]:
    return list(db.scalars(select(AgentRun).where(AgentRun.id.in_(ids)).order_by(AgentRun.id))) if ids else []


def _lang(conv: Conversation) -> str:
    return lang_svc.reply_lang(conv.language, conv.script)


def _set_language(conv: Conversation, language: str, script: str) -> None:
    conv.language, conv.script = language, script


def _turn_language(prev_language: str | None, prev_script: str | None, intake: IntakeResult,
                   parsed_language: str | None = None) -> str:
    """Reply language for this turn. Marker words in the message win; otherwise the conversation keeps its language
    (so "pav kilo coriander" does not flip a Hinglish chat to English); the parser's guess is the last resort."""
    if intake.script == "devanagari":
        if intake.confident or parsed_language not in ("hindi", "marathi"):
            return intake.language
        return parsed_language
    if intake.confident:
        return intake.language
    if prev_language and prev_script == "latin":
        return prev_language
    return parsed_language or intake.language


def _say(t: _Turn, text: str, meta: dict | None = None) -> None:
    """Store the bot reply. Every reply of an order with open questions carries their ids, so the chips under the
    latest bot message never disappear (e.g. after "ruko" or an off-topic message)."""
    if t.order is not None and not (meta and "clarification_ids" in meta):
        open_ids = [c.id for c in orders_svc.open_clarifications(t.ctx.db, t.order.id)]
        if open_ids:
            meta = {**(meta or {}), "order_id": t.order.id, "clarification_ids": open_ids}
    t.bot = run_messaging(t.ctx, text, meta)


def _finish_order_message(
    t: _Turn, intake_language: str, intake_script: str, current_ids: set[int] | None = None,
    added: list[str] | None = None,
) -> None:
    """After the order lines are saved. The bot asks about the questions raised by THIS message (`current_ids`;
    None = every open one, used when answering). Older questions that are still open stay as chips and in the draft,
    and get a short reminder only when this message raised nothing new. Nothing open: "order ready"."""
    db, order = t.ctx.db, t.order
    assert order is not None
    orders_svc.refresh_status(db, order)
    open_all = orders_svc.open_clarifications(db, order.id)
    meta = {"order_id": order.id, "clarification_ids": [c.id for c in open_all]}
    asking = [c for c in open_all if current_ids is None or c.id in current_ids]
    if asking:
        facts = orders_svc.clarification_facts(db, order, t.products, {c.id for c in asking})
        res = run_clarifier(t.ctx, t.conv.language or intake_language, t.conv.script or intake_script,
                            t.shop.name, facts, t.customer_text)
        _say(t, res.message, meta)
    elif open_all:
        items = {i.id: i for i in orders_svc.order_items(db, order.id)}
        names = [items[c.order_item_id].name_guess for c in open_all]
        t.ctx.skipped("clarifier", "nothing new to ask; reminded about pending items")
        _say(t, lang_svc.pending_reminder(_lang(t.conv), names), meta)
    else:
        t.ctx.skipped("clarifier", "nothing left to ask")
        # name what this message added, so "order ready" never reads like a repeat of the previous reply
        _say(t, lang_svc.ready_after_adding(_lang(t.conv), added or []), meta)


def _process_items(t: _Turn, parsed, intake: IntakeResult) -> None:
    db = t.ctx.db
    plans = [ItemPlan(parsed=p, qty=q) for p, q in parsed.items]
    run_matcher(t.ctx, t.index, plans)
    run_inventory(t.ctx, plans, t.catalog)
    if t.order is None:
        t.order = orders_svc.create_order(db, t.conv)
    if parsed.delivery_time_text:
        t.order.requested_delivery_text = parsed.delivery_time_text[:200]
    created = orders_svc.save_plans(db, t.order, plans, _lang(t.conv))
    added = [f"{p.product.name} {orders_svc.qty_text(p.product, p.product_qty)}".strip()
             for p in plans if p.status == "matched" and p.product is not None]
    _finish_order_message(t, intake.language, intake.script, {c.id for c in created}, added)


def _answer_availability(t: _Turn, parsed, text: str, lang: str) -> bool:
    """"Shakkar hai?": look the product up in the catalog and DB stock and say what the shop has. The order is not
    touched. Returns False when this is not an availability question after all (an order-status question)."""
    # the parser sometimes drops the quantity ("ek kilo ..."); for a single item it is read from the message itself
    from_text = extract_quantity(text) if len(parsed.items) == 1 else None
    asks = [(it.name_guess, it.brand_guess, q if q.value is not None else from_text)
            for it, q in parsed.items if it.name_guess]
    if not asks:  # the parser gave no item: use the product words of the question itself
        words = availability_agent.question_words(text)
        asks = [(words, None, extract_quantity(text))] if words else []
    if not asks:
        return False
    entries = availability_agent.run_availability(t.ctx, t.index, t.catalog, asks)
    ask_qty = {w: q for w, _, q in asks if q is not None}
    if parsed.intent == "status_query" and not any(e.found for e in entries):
        return False  # "mera order kahan hai": no product involved, not an availability question
    facts = [
        {
            "word": e.word,
            "products": [
                {"label": availability_agent.label(p), "in_stock": p.stock_qty > 0,
                 "low": 0 < p.stock_qty <= p.low_stock_threshold, "left": availability_agent.left_text(p)}
                for p in e.products
            ],
            "substitutes": [availability_agent.label(p) for p in e.substitutes],
            "fit": None if e.fit is None else {
                "qty": availability_agent.qty_label(ask_qty[e.word]), "label": e.fit.product.name,
                "n": orders_svc.qty_text(e.fit.product, e.fit.product_qty) if e.fit.product.sell_mode == "pack" else "",
                "ok": e.fit.ok, "avail": availability_agent.left_text(e.fit.product),
            },
        }
        for e in entries
    ]
    _say(t, lang_svc.availability_reply(lang, facts), {"reason": "availability"})
    return True


def _confirm_reply(t: _Turn, lang: str) -> None:
    """"Haan, bill bana do": Stage 4 will make the bill and confirm. Until then nothing is confirmed, and the customer is
    told so, with the draft read back. Pending questions come first."""
    db, order = t.ctx.db, t.order
    open_all = orders_svc.open_clarifications(db, order.id) if order else []
    if open_all:
        items = {i.id: i for i in orders_svc.order_items(db, order.id)}
        names = ", ".join(dict.fromkeys(items[c.order_item_id].name_guess for c in open_all))
        _say(t, lang_svc.fixed("confirm_pending", lang).format(names=names), {"reason": "confirm_pending"})
        return
    summary = orders_svc.line_summary(db, order, t.products) if order else ""
    if not summary:
        _say(t, lang_svc.fixed("empty_order", lang), {"reason": "confirm_empty"})
        return
    _say(t, lang_svc.fixed("confirm_stage3", lang).format(summary=summary), {"reason": "confirm_not_available_yet"})


def _decline_reply(t: _Turn, lang: str) -> None:
    """"Nahi" to "Bill banaun?": no bill for now, the draft stays exactly as it is."""
    db, order = t.ctx.db, t.order
    summary = orders_svc.line_summary(db, order, t.products) if order else ""
    key, kw = ("declined", {"summary": summary}) if summary else ("declined_empty", {})
    _say(t, lang_svc.fixed(key, lang).format(**kw), {"reason": "declined"})


def _pick_clarification(t: _Turn, text: str, open_clars: list[Clarification]) -> Clarification | None:
    """Which open question does a free-text reply answer? One open -> that one; several -> the best fuzzy fit."""
    if len(open_clars) == 1:
        return open_clars[0]
    words = answer_agent._name_tokens(text)
    best, best_score = None, 0.0
    for c in open_clars:
        offered = [o["product_id"] for o in (c.options or [])]
        if words and offered:
            res = match(words, t.index.restrict(offered))
            top = max((cand.score for cand in res.candidates), default=0.0)
            if top > best_score:
                best, best_score = c, top
    if best is not None and best_score >= 85:
        return best
    vague = [c for c in open_clars if c.kind == "vague_qty"]
    if len(vague) == 1 and normalize(text).value is not None and not words:
        return vague[0]
    return None


def _answer_turn(
    t: _Turn, clar: Clarification | None, open_clars: list[Clarification], option_product_id: int | None,
    text: str | None, intake_language: str, intake_script: str,
) -> None:
    db = t.ctx.db
    order = t.order
    assert order is not None
    if clar is None:  # could not tell which question the reply is for
        _say(t, lang_svc.fixed("reask", _lang(t.conv)),
             {"order_id": order.id, "clarification_ids": [c.id for c in open_clars]})
        return
    item = db.get(OrderItem, clar.order_item_id)
    d = answer_agent.run_answer_matcher(t.ctx, clar, item, option_product_id, text, t.index, t.catalog)
    d = answer_agent.run_answer_inventory(t.ctx, d, t.catalog)
    if d.action == "reask":
        _say(t, lang_svc.fixed("reask", _lang(t.conv)),
             {"order_id": order.id, "clarification_ids": [c.id for c in open_clars]})
        return
    answer_agent.apply_decision(db, order, clar, item, d, _lang(t.conv), option_product_id, text)
    _finish_order_message(t, intake_language, intake_script)


def _finalize(t: _Turn, new_msgs: list[Message]) -> ChatResult:
    db = t.ctx.db
    order = t.order
    if order is not None:
        orders_svc.link_runs_to_order(db, t.ctx.run_ids, order.id)
    db.commit()
    if t.bot is not None:
        new_msgs.append(t.bot)
    return ChatResult(new_msgs, order, _load_runs(db, t.ctx.run_ids))


def _failure(t: _Turn, new_msgs: list[Message]) -> ChatResult:
    """An LLM step failed or returned invalid output: nothing is written to the order."""
    db = t.ctx.db
    db.rollback()
    t.order = orders_svc.active_order(db, t.conv.id)  # as it was before this message
    t.ctx.order_id = t.order.id if t.order else None
    _say(t, lang_svc.fixed("failure", lang_svc.reply_lang(t.conv.language, t.conv.script)), {"error": "LLM_FAILED"})
    res = _finalize(t, new_msgs)
    res.failed = True
    return res


def _new_turn(db: Session, conv: Conversation, shop: Shop, customer_text: str, meta: dict | None = None) -> tuple[_Turn, Message]:
    ctx = RunCtx(db=db, conversation_id=conv.id)
    cust = Message(conversation_id=conv.id, sender="customer", type="text", content=customer_text, meta=meta)
    db.add(cust)
    db.commit()  # the customer's message is kept even if a later step fails
    ctx.message_id = cust.id
    # Serialise messages of one conversation (two quick sends must not both create an order). NO KEY UPDATE does not
    # block the agent_runs rows, which are written by separate sessions and only take a key-share lock on this row.
    db.execute(select(Conversation.id).where(Conversation.id == conv.id).with_for_update(key_share=True))
    catalog = orders_svc.load_catalog(db, shop.id)
    order = orders_svc.active_order(db, conv.id)
    ctx.order_id = order.id if order else None
    t = _Turn(ctx, conv, shop, catalog, CatalogIndex(catalog), order, customer_text, products={p.id: p for p in catalog})
    return t, cust


def handle_text_message(db: Session, conv: Conversation, shop: Shop, text: str) -> ChatResult:
    t, cust = _new_turn(db, conv, shop, text)
    msgs = [cust]
    try:
        prev_language, prev_script = conv.language, conv.script
        intake = run_intake(t.ctx, text, t.index.vocabulary())
        _set_language(conv, _turn_language(prev_language, prev_script, intake), intake.script)
        lang = _lang(conv)

        if intake.category == "wait":  # "ruko": keep the order exactly as it is
            kept = t.order is not None and any(i.status != "removed" for i in orders_svc.order_items(db, t.order.id))
            _say(t, lang_svc.fixed("wait" if kept else "wait_empty", lang), {"reason": "wait"})
            return _finalize(t, msgs)

        open_clars = orders_svc.open_clarifications(db, t.order.id) if t.order else []
        if intake.category in ("confirm", "decline") and not open_clars:
            # a short "haan, bill bana do" / "nahi" answers the bot's "Bill banaun?". With an open question the
            # parser decides instead ("nahi" may be an answer to that question).
            (_confirm_reply if intake.category == "confirm" else _decline_reply)(t, lang)
            return _finalize(t, msgs)

        if intake.category == "gibberish":
            # the "language" of random letters is meaningless: Roman-script gibberish gets the Hinglish reply
            lang = lang_svc.reply_lang("hinglish" if intake.script == "latin" else intake.language, intake.script)
            _say(t, lang_svc.fixed("repeat", lang), {"reason": "gibberish"})
            return _finalize(t, msgs)
        if intake.category == "other":
            _say(t, lang_svc.fixed("other", lang), {"reason": "not_an_order"})
            return _finalize(t, msgs)

        questions = [c.question for c in open_clars]
        parsed = run_parser(t.ctx, text, intake, sorted({p.category for p in t.catalog}),
                            orders_svc.order_summary_text(db, t.order), questions)
        _set_language(conv, _turn_language(prev_language, prev_script, intake, parsed.language), intake.script)
        lang = _lang(conv)

        # "ek kilo biscuit hai" (question) vs "ek kilo biscuit de do" (request): the LLM's reading of "hai" varies,
        # so clear words decide, in both directions
        signal = availability_agent.classify(text)
        if parsed.intent in ("new_order", "add_items") and signal == "question":
            parsed.intent = "availability_query"
        elif parsed.intent == "availability_query" and signal == "order":
            parsed.intent = "add_items"

        if parsed.intent in AVAILABILITY_INTENTS and _answer_availability(t, parsed, text, lang):
            pass  # answered from the catalog; the order is untouched
        elif parsed.intent == "gibberish":
            _say(t, lang_svc.fixed("repeat", lang), {"reason": "gibberish"})
        elif parsed.intent == "other":
            _say(t, lang_svc.fixed("other", lang), {"reason": "not_an_order"})
        elif parsed.intent == "answer_clarification" and open_clars and not parsed.items:
            clar = _pick_clarification(t, text, open_clars)
            _answer_turn(t, clar, open_clars, None, text, intake.language, intake.script)
        elif parsed.intent == "confirm" and not parsed.items:
            _confirm_reply(t, lang)
        elif parsed.intent == "cancel" and not parsed.items and lang_svc.is_skip(text):
            if open_clars:  # "nahi" about the item we just asked about = skip that item
                _answer_turn(t, _pick_clarification(t, text, open_clars), open_clars, None, text,
                             intake.language, intake.script)
            else:
                _decline_reply(t, lang)
        elif parsed.intent in UNSUPPORTED_INTENTS and not parsed.items:
            meta = {"order_id": t.order.id} if t.order else None
            _say(t, lang_svc.fixed("unsupported", lang), meta)
        elif not parsed.items:
            _say(t, lang_svc.fixed("repeat", lang), {"reason": "no_items"})
        else:
            _process_items(t, parsed, intake)
        return _finalize(t, msgs)
    except TooManyItems:
        db.rollback()
        t.order = orders_svc.active_order(db, conv.id)
        _say(t, lang_svc.fixed("too_many", _lang(conv)), {"reason": "too_many_items"})
        return _finalize(t, msgs)
    except (LLMError, ValidationError) as e:
        log.warning("LLM step failed, nothing written to the order: %s", e)
        return _failure(t, msgs)


def handle_clarification_answer(
    db: Session, conv: Conversation, shop: Shop, clar: Clarification, option_product_id: int | None, text: str | None,
) -> ChatResult:
    """POST /conversations/{id}/clarifications/{cid}/answer"""
    label = text or ""
    if option_product_id is not None:
        label = next((o["label"] for o in (clar.options or []) if o["product_id"] == option_product_id), str(option_product_id))
    meta = {"clarification_id": clar.id}
    if option_product_id is not None:
        meta["option_product_id"] = option_product_id
    t, cust = _new_turn(db, conv, shop, label, meta)
    msgs = [cust]
    try:
        open_clars = orders_svc.open_clarifications(db, clar.order_id)
        clar = db.get(Clarification, clar.id)
        _answer_turn(t, clar, open_clars, option_product_id, text, conv.language or "hinglish", conv.script or "latin")
        return _finalize(t, msgs)
    except (LLMError, ValidationError) as e:
        log.warning("LLM step failed during an answer: %s", e)
        return _failure(t, msgs)
