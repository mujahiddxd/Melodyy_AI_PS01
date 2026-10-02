"""Cheap, deterministic language / script / gibberish checks for the Intake agent, and the fixed reply texts used when
no LLM wording is needed (order ready, "please repeat", failures) or as a fallback when the clarifier LLM fails."""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services import unit_normalizer as un
from app.services.matcher import norm

_DEVA = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")

_MARATHI_DEVA = {"आणि", "पाठवा", "पाहिजे", "हवे", "हवा", "हवी", "द्या", "दोन", "अर्धा", "अर्ध", "कृपया", "मला", "आहे",
                 "तांदूळ", "साखर", "कांदा", "बटाटा", "डाळ", "चहा", "साबण", "पुडा", "डझन", "नको", "अडीच", "दीड", "वीस"}
_HINDI_DEVA = {"और", "चाहिए", "भेज", "का", "की", "है", "मुझे", "चावल", "चीनी", "आटा", "नमक", "दो", "पैकेट", "दे", "दीजिए",
               "आधा", "डेढ़", "ढाई", "कृपया"}
_MARATHI_LATIN = {"ani", "pahije", "pahijet", "dya", "mala", "hava", "havi", "kiti", "aahe", "ardha", "tandul",
                  "sakhar", "kanda", "batata", "pathva", "nako", "adich", "didh"}
_HINGLISH = {"bhaiya", "bhai", "bhaiyya", "aur", "chahiye", "chahie", "bhej", "bhejo", "ek", "teen", "char",
             "thoda", "bhi", "hai", "mujhe", "de", "dena", "dijiye", "kar", "karo", "kilo", "namak", "cheeni", "tel",
             "atta", "chawal", "doodh", "wala", "nahi", "haan", "kya", "kal", "aadha", "adha", "pav", "dedh", "dhai"}
_ENGLISH = {"i", "want", "need", "please", "send", "and", "of", "me", "the", "a", "an", "some", "with", "also",
            "give", "get", "would", "like", "kg", "litre", "liter", "bread", "milk", "rice", "sugar", "oil", "salt",
            "eggs", "tea", "half", "one", "two", "three", "you", "your", "have", "does", "is", "are", "there",
            "any", "in", "stock", "available", "got", "can", "could", "what", "how", "much", "price", "buy"}
_FILLER_KNOWN = {"kg", "g", "gm", "l", "ml", "pc", "pcs", "packet", "pkt", "ok", "okay", "yes", "no", "hi", "hello",
                 "namaste", "haan", "han", "nahi", "bill", "order", "confirm", "cancel"}


# "ruko" / "wait" / "थांबा": the customer is pausing. The order is kept untouched.
_WAIT_KEYS = {"ruko", "ruk", "rukiye", "rukho", "rukna", "wait", "hold", "thamba", "thamb", "thambaa",
              "रुको", "रुकिए", "रुकें", "रुक", "ठहरो", "ठहरिए", "थांबा", "थांब", "थांबा"}
_WAIT_MARATHI = {"thamba", "thamb", "thambaa", "थांबा", "थांब"}
_WAIT_HINDI = {"ruko", "ruk", "rukiye", "rukho", "rukna", "रुको", "रुकिए", "रुकें", "रुक", "ठहरो", "ठहरिए"}
_WAIT_FILLER = {"bhai", "bhaiya", "bhaiyya", "ek", "minute", "min", "sec", "second", "zara", "jara", "thoda", "please",
                "pls", "on", "a", "jao", "ja", "ji", "na", "भाई", "भैया", "एक", "मिनट", "मिनिट", "ज़रा", "जरा", "थोडा",
                "थोड़ा", "ना", "जी"}


# "Haan, bill bana do" / "Nahi": short replies to the bot's "Bill banaun?". Only trusted when nothing is pending
# (with an open question, "nahi" may be an answer to it, so the parser decides).
_CONFIRM_KEYS = {"haan", "han", "ha", "yes", "yep", "ok", "okay", "confirm", "bill", "thik", "theek", "हाँ", "हां",
                 "ठीक", "बिल", "होय", "हो"}
_CONFIRM_FILLER = {"bana", "banao", "bana", "do", "dijiye", "dena", "kar", "karo", "kardo", "ji", "hai", "please", "pls",
                   "bhai", "bhaiya", "abhi", "bilkul", "sure", "it", "the", "बना", "बनाओ", "दो", "कर", "करो", "जी",
                   "है", "भाई", "भैया", "बनवा", "करा", "द्या", "बनवू"}
_DECLINE_KEYS = {"nahi", "nahin", "nai", "no", "nope", "mat", "nako", "नहीं", "नही", "नको", "मत", "rehne", "rahne",
                 "रहने", "रहेने"}
_DECLINE_FILLER = {"abhi", "do", "rehne", "rahne", "bas", "thank", "thanks", "bhai", "bhaiya", "ji", "hai", "chahiye",
                   "अभी", "दो", "बस", "भाई", "जी", "है", "चाहिए", "द्या", "आत्ता"}


@dataclass
class Assessment:
    script: str  # latin | devanagari
    language: str  # hinglish | hindi | marathi | english
    verdict: str  # ok | gibberish | uncertain | wait | confirm | decline
    reason: str
    confident: bool = False  # the language came from marker words, not from the default


def detect_script(text: str) -> str:
    deva, latin = len(_DEVA.findall(text)), len(_LATIN.findall(text))
    return "devanagari" if deva > latin else "latin"


def _known_words(catalog_vocab: set[str]) -> set[str]:
    words = set(un._NUMBER_WORDS) | set(un._UNITS) | set(un._FRAC_MULT) | set(un._FRAC_ABS) | set(un._MODIFIERS)
    words |= un.VAGUE_WORDS | _HINGLISH | _ENGLISH | _MARATHI_LATIN | _FILLER_KNOWN | catalog_vocab
    return {norm(w) for w in words}


def assess(text: str, catalog_vocab: set[str] | None = None) -> Assessment:
    script = detect_script(text)
    tokens = norm(text).split()
    tokset = set(tokens)

    if script == "devanagari":
        mr_d, hi_d = len(tokset & _MARATHI_DEVA), len(tokset & _HINDI_DEVA)
        language = "marathi" if mr_d >= max(1, hi_d) else "hindi"
        confident = bool(mr_d or hi_d)
    else:
        mr, hi, en = len(tokset & _MARATHI_LATIN), len(tokset & _HINGLISH), len(tokset & _ENGLISH)
        if mr and mr >= hi:
            language = "marathi"
        elif en and not hi:
            language = "english"
        else:
            language = "hinglish"
        confident = bool(mr or hi or en)

    if tokens and len(tokens) <= 5 and tokset & _WAIT_KEYS and tokset <= (_WAIT_KEYS | _WAIT_FILLER):
        if tokset & _WAIT_MARATHI:
            language = "marathi"
        elif tokset & {"wait", "hold"} and not tokset & _WAIT_HINDI:
            language = "english"
        elif tokset & _WAIT_HINDI:
            language = "hindi" if script == "devanagari" else "hinglish"
        return Assessment(script, language, "wait", "customer asked us to wait", True)

    if tokens and len(tokens) <= 5 and tokset & _CONFIRM_KEYS and tokset <= (_CONFIRM_KEYS | _CONFIRM_FILLER):
        return Assessment(script, language, "confirm", "short confirmation", confident)
    if tokens and len(tokens) <= 4 and tokset & _DECLINE_KEYS and tokset <= (_DECLINE_KEYS | _DECLINE_FILLER):
        return Assessment(script, language, "decline", "short refusal", confident)

    chars = [c for c in text if not c.isspace()]
    letters = [c for c in chars if c.isalpha() or "ऀ" <= c <= "ॿ"]
    if not chars or len(letters) / len(chars) < 0.4 or (not letters):
        return Assessment(script, language, "gibberish", "no letters (symbols/emoji only)", confident)
    if script == "devanagari":
        return Assessment(script, language, "ok", "devanagari text, parser decides", confident)
    known = _known_words(catalog_vocab or set())
    if any(t in known or any(ch.isdigit() for ch in t) for t in tokens):
        return Assessment(script, language, "ok", "recognised words", confident)
    return Assessment(script, language, "uncertain", "no recognised words", confident)


# ---- reply texts ----------------------------------------------------------------------------------------
def reply_lang(language: str | None, script: str | None) -> str:
    """Template language. Marathi typed in Roman letters gets the Hinglish templates."""
    if script == "devanagari":
        return "marathi" if language == "marathi" else "hindi"
    if language == "english":
        return "english"
    return "hinglish"


FIXED = {
    "repeat": {
        "hinglish": "Maaf kijiye, mujhe samajh nahi aaya. Kripya apna order dobara likhiye, jaise \"2 kilo atta aur ek packet namak\".",
        "hindi": "माफ़ कीजिए, मैं समझ नहीं पाया। कृपया अपना ऑर्डर दोबारा लिखिए, जैसे \"2 किलो आटा और एक पैकेट नमक\"।",
        "marathi": "माफ करा, मला समजले नाही. कृपया तुमची ऑर्डर पुन्हा लिहा, उदा. \"2 किलो पीठ आणि एक पुडा मीठ\".",
        "english": "Sorry, I couldn't understand that. Please type your order again, like \"2 kg atta and 1 packet salt\".",
    },
    "other": {
        "hinglish": "Main yahan grocery orders mein madad karta hoon. Bataiye, kya chahiye? Jaise \"2 kilo atta aur ek packet namak\".",
        "hindi": "मैं यहाँ किराना ऑर्डर में मदद करता हूँ। बताइए, क्या चाहिए? जैसे \"2 किलो आटा और एक पैकेट नमक\"।",
        "marathi": "मी इथे किराणा ऑर्डरसाठी मदत करतो. सांगा, काय हवे? उदा. \"2 किलो पीठ आणि एक पुडा मीठ\".",
        "english": "I can help with grocery orders here. What would you like? For example \"2 kg atta and 1 packet salt\".",
    },
    "failure": {
        "hinglish": "Thoda problem hua, dobara bhejiye",
        "hindi": "थोड़ी दिक्कत हुई, दोबारा भेजिए",
        "marathi": "थोडी अडचण आली, पुन्हा पाठवा",
        "english": "Thoda problem hua, dobara bhejiye",
    },
    "ready": {
        "hinglish": "Order ready hai ✅ Bill neeche hai, dekh ke confirm kijiye.",
        "hindi": "ऑर्डर तैयार है ✅ बिल नीचे है, देखकर कन्फ़र्म कीजिए।",
        "marathi": "ऑर्डर तयार आहे ✅ बिल खाली आहे, पाहून कन्फर्म करा.",
        "english": "Your order is ready ✅ The bill is below, please check and confirm.",
    },
    "too_many": {
        "hinglish": "Ek baar mein 30 se zyada items nahi le sakta. Thoda kam karke dobara bhejiye.",
        "hindi": "एक बार में 30 से ज़्यादा आइटम नहीं ले सकता। थोड़ा कम करके दोबारा भेजिए।",
        "marathi": "एकावेळी 30 पेक्षा जास्त वस्तू घेता येत नाहीत. थोड्या कमी करून पुन्हा पाठवा.",
        "english": "I can't take more than 30 items at once. Please send fewer items.",
    },
    "unsupported": {
        "hinglish": "Ye option abhi aa raha hai. Abhi aap naye items likh sakte hain.",
        "hindi": "यह सुविधा अभी आ रही है। अभी आप नए आइटम लिख सकते हैं।",
        "marathi": "ही सुविधा लवकरच येत आहे. सध्या तुम्ही नवीन वस्तू लिहू शकता.",
        "english": "That option is coming soon. For now you can add new items.",
    },
    "reask": {
        "hinglish": "Samajh nahi aaya. Neeche se chun lijiye ya dobara likhiye.",
        "hindi": "समझ नहीं आया। नीचे से चुनिए या दोबारा लिखिए।",
        "marathi": "समजले नाही. खाली निवडा किंवा पुन्हा लिहा.",
        "english": "I didn't get that. Please pick an option below or type it again.",
    },
    "wait": {
        "hinglish": "Theek hai bhai, aap aaram se batao. Main aapka current order yahin rakhta hoon.",
        "hindi": "ठीक है भाई, आप आराम से बताइए। मैं आपका मौजूदा ऑर्डर यहीं रखता हूँ।",
        "marathi": "ठीक आहे, तुम्ही निवांत सांगा. मी तुमची सध्याची ऑर्डर इथेच ठेवतो.",
        "english": "Sure, take your time. I'll keep your current order right here.",
    },
    "wait_empty": {
        "hinglish": "Theek hai bhai, aap aaram se batao.",
        "hindi": "ठीक है भाई, आप आराम से बताइए।",
        "marathi": "ठीक आहे, तुम्ही निवांत सांगा.",
        "english": "Sure, take your time.",
    },
    "confirm_use_button": {
        "hinglish": "Samajh gaya. Order confirm karne ke liye bill card ka \"Confirm order\" button dabaiye (phone verify aur delivery address zaroori hai). Aapka order: {summary}.",
        "hindi": "समझ गया। ऑर्डर कन्फ़र्म करने के लिए बिल कार्ड का \"Confirm order\" बटन दबाइए (फ़ोन वेरिफ़ाई और डिलीवरी पता ज़रूरी है)। आपका ऑर्डर: {summary}।",
        "marathi": "समजले. ऑर्डर कन्फर्म करण्यासाठी बिल कार्डवरील \"Confirm order\" बटण दाबा (फोन व्हेरिफाय आणि डिलिव्हरी पत्ता आवश्यक आहे). तुमची ऑर्डर: {summary}.",
        "english": "Got it. Tap \"Confirm order\" on the bill card to place the order (phone verification and a delivery address are needed). Your order: {summary}.",
    },
    "confirm_pending": {
        "hinglish": "Pehle in items ka jawab de dijiye: {names}. Phir bill ban jayega.",
        "hindi": "पहले इन आइटम का जवाब दे दीजिए: {names}। फिर बिल बन जाएगा।",
        "marathi": "आधी या वस्तूंचे उत्तर द्या: {names}. मग बिल बनेल.",
        "english": "Please answer these first: {names}. Then I can make the bill.",
    },
    "declined": {
        "hinglish": "Theek hai, order abhi confirm nahi karte. Aapka order yahin hai: {summary}. Aur kuch jodna ho toh bataiye.",
        "hindi": "ठीक है, ऑर्डर अभी कन्फ़र्म नहीं करते। आपका ऑर्डर यहीं है: {summary}। और कुछ जोड़ना हो तो बताइए।",
        "marathi": "ठीक आहे, ऑर्डर आत्ता कन्फर्म करत नाही. तुमची ऑर्डर इथेच आहे: {summary}. आणखी काही जोडायचे असल्यास सांगा.",
        "english": "Okay, we won't confirm the order yet. Your order stays here: {summary}. Tell me if you want to add anything.",
    },
    "declined_empty": {
        "hinglish": "Theek hai. Jab chahiye tab bata dijiye.",
        "hindi": "ठीक है। जब चाहिए तब बता दीजिए।",
        "marathi": "ठीक आहे. हवे तेव्हा सांगा.",
        "english": "Okay. Tell me whenever you need something.",
    },
    "empty_order": {
        "hinglish": "Abhi order mein koi item nahi hai. Bataiye, kya chahiye?",
        "hindi": "अभी ऑर्डर में कोई आइटम नहीं है। बताइए, क्या चाहिए?",
        "marathi": "सध्या ऑर्डरमध्ये कोणतीही वस्तू नाही. सांगा, काय हवे?",
        "english": "There are no items in the order yet. What would you like?",
    },
}

ADDED = {
    "hinglish": "Jod diya: {added}.",
    "hindi": "जोड़ दिया: {added}।",
    "marathi": "जोडले: {added}.",
    "english": "Added: {added}.",
}


STATUS_MESSAGES = {
    "confirmed": {
        "hinglish": "Order #{no} confirm ho gaya ✓ Dukaan aapka order jaldi pack karegi.",
        "hindi": "ऑर्डर #{no} कन्फ़र्म हो गया ✓ दुकान जल्द ही आपका ऑर्डर पैक करेगी।",
        "marathi": "ऑर्डर #{no} कन्फर्म झाली ✓ दुकान लवकरच तुमची ऑर्डर पॅक करेल.",
        "english": "Order #{no} confirmed ✓ The shop will pack it soon.",
    },
    "packing": {
        "hinglish": "Order #{no} pack ho raha hai 📦",
        "hindi": "ऑर्डर #{no} पैक हो रहा है 📦",
        "marathi": "ऑर्डर #{no} पॅक होत आहे 📦",
        "english": "Order #{no} is being packed 📦",
    },
    "out_for_delivery": {
        "hinglish": "Order #{no} delivery ke liye nikal gaya 🛵",
        "hindi": "ऑर्डर #{no} डिलीवरी के लिए निकल गया 🛵",
        "marathi": "ऑर्डर #{no} डिलिव्हरीसाठी निघाली 🛵",
        "english": "Order #{no} is out for delivery 🛵",
    },
    "delivered": {
        "hinglish": "Order #{no} deliver ho gaya ✅ Dhanyavaad!",
        "hindi": "ऑर्डर #{no} डिलीवर हो गया ✅ धन्यवाद!",
        "marathi": "ऑर्डर #{no} डिलिव्हर झाली ✅ धन्यवाद!",
        "english": "Order #{no} delivered ✅ Thank you!",
    },
    "cancelled": {
        "hinglish": "Order #{no} cancel ho gaya.",
        "hindi": "ऑर्डर #{no} रद्द हो गया।",
        "marathi": "ऑर्डर #{no} रद्द झाली.",
        "english": "Order #{no} was cancelled.",
    },
}


def ready_after_adding(lang: str, added: list[str]) -> str:
    """"Order ready" that also says what this message changed, so it never reads like a repeated reply."""
    if not added:
        return FIXED["ready"][lang]
    return ADDED[lang].format(added=", ".join(added)) + " " + FIXED["ready"][lang]


PENDING = {
    "hinglish": "Theek hai, order mein jod diya ✅ In items ka jawab abhi baaki hai: {names}. Neeche chun lijiye ya \"skip\" likhiye.",
    "hindi": "ठीक है, ऑर्डर में जोड़ दिया ✅ इन आइटम का जवाब अभी बाकी है: {names}। नीचे चुनिए या \"skip\" लिखिए।",
    "marathi": "ठीक आहे, ऑर्डरमध्ये जोडले ✅ या वस्तूंचे उत्तर अजून बाकी आहे: {names}. खाली निवडा किंवा \"skip\" लिहा.",
    "english": "Added to your order ✅ Still waiting for your answer on: {names}. Pick below or type \"skip\".",
}


def pending_reminder(lang: str, names: list[str]) -> str:
    return PENDING[lang].format(names=", ".join(dict.fromkeys(names)))


_OR = {"hinglish": "ya", "hindi": "या", "marathi": "किंवा", "english": "or"}
_FOOTER = {
    "hinglish": "Neeche se chun lijiye ya likh dijiye.",
    "hindi": "नीचे से चुन लीजिए या लिख दीजिए।",
    "marathi": "खाली निवडा किंवा लिहून सांगा.",
    "english": "Tap an option below or just type it.",
}
SKIP_WORDS = {
    "skip", "remove", "cancel", "nahi", "nahin", "nai", "no", "rehne do", "rahne do", "chhod do", "chod do", "hata do",
    "nahi chahiye", "nako", "नहीं", "नही", "रहने दो", "छोड़ दो", "हटा दो", "नको", "नहीं चाहिए",
}


def fixed(key: str, lang: str) -> str:
    return FIXED[key][lang]


def is_skip(text: str) -> bool:
    t = norm(text)
    return t in {norm(w) for w in SKIP_WORDS}


def _join(options: list[str], lang: str) -> str:
    if len(options) <= 1:
        return "".join(options)
    return ", ".join(options[:-1]) + f" {_OR[lang]} " + options[-1]


def _opt_names(options: list[dict]) -> list[str]:
    return [o["name"] for o in options]


def item_question(lang: str, word: str, kind: str, name: str | None, options: list[dict], available: str | None) -> str:
    """One short question about one item (stored in clarifications.question, also the template fallback line)."""
    opts = _join(_opt_names(options), lang)
    zero = available in (None, "0", "0.000")
    t = {
        "hinglish": {
            "ambiguous_product": f"{word}: kaunsa chahiye — {opts}?",
            "pack_size": f"{word}: kaunsa pack chahiye — {opts}?",
            "out_of_stock": (f"{name} abhi stock mein nahi hai." if zero else f"{name} mein sirf {available} available hai.")
                            + (f" {opts} chalega?" if options else ""),
            "unmatched": f"{word} hamare paas nahi mila.",
            "vague_qty": f"{word} kitna chahiye — 1 kilo, 2 kilo?",
        },
        "hindi": {
            "ambiguous_product": f"{word}: कौन सा चाहिए — {opts}?",
            "pack_size": f"{word}: कौन सा पैक चाहिए — {opts}?",
            "out_of_stock": (f"{name} अभी स्टॉक में नहीं है।" if zero else f"{name} में सिर्फ़ {available} उपलब्ध है।")
                            + (f" {opts} चलेगा?" if options else ""),
            "unmatched": f"{word} हमारे पास नहीं मिला।",
            "vague_qty": f"{word} कितना चाहिए — 1 किलो, 2 किलो?",
        },
        "marathi": {
            "ambiguous_product": f"{word}: कोणता हवा — {opts}?",
            "pack_size": f"{word}: कोणता पॅक हवा — {opts}?",
            "out_of_stock": (f"{name} सध्या स्टॉकमध्ये नाही." if zero else f"{name} फक्त {available} उपलब्ध आहे.")
                            + (f" {opts} चालेल का?" if options else ""),
            "unmatched": f"{word} आमच्याकडे मिळाले नाही.",
            "vague_qty": f"{word} किती हवे — 1 किलो, 2 किलो?",
        },
        "english": {
            "ambiguous_product": f"{word}: which one — {opts}?",
            "pack_size": f"{word}: which pack — {opts}?",
            "out_of_stock": (f"{name} is out of stock right now." if zero else f"Only {available} of {name} available.")
                            + (f" Would {opts} work?" if options else ""),
            "unmatched": f"We couldn't find {word}.",
            "vague_qty": f"How much {word} do you need — 1 kg, 2 kg?",
        },
    }
    return t[lang][kind]


def combined_message(lang: str, items: list[dict]) -> str:
    """Template version of the clarifier's ONE combined message (fallback when the LLM fails or is invalid)."""
    lines = [
        item_question(lang, i["customer_word"], i["problem"], i.get("name"), i.get("options", []), i.get("available"))
        for i in items
    ]
    return " ".join(lines + [_FOOTER[lang]])


_AVAIL = {
    "hinglish": {
        "one": "Haan, {label} available hai.", "many": "Haan, {word} mein ye available hain: {labels}.",
        "low": " (sirf {n} bacha)", "out": " (abhi stock mein nahi)",
        "none_in_stock": "{labels} abhi stock mein nahi hai.", "subs": " Ye available hain: {labels}.",
        "hint": "Order mein jodna ho toh batayiye, jaise \"1 kilo\".",
        "fit_ok": " {qty} ke liye {label} {n} mil jayega.",
        "fit_short": " {qty} ke liye {label} mein itna stock nahi hai (sirf {avail} available).",
    },
    "hindi": {
        "one": "हाँ, {label} उपलब्ध है।", "many": "हाँ, {word} में ये उपलब्ध हैं: {labels}।",
        "low": " (सिर्फ़ {n} बचा)", "out": " (अभी स्टॉक में नहीं)",
        "none_in_stock": "{labels} अभी स्टॉक में नहीं है।", "subs": " ये उपलब्ध हैं: {labels}।",
        "hint": "ऑर्डर में जोड़ना हो तो बताइए, जैसे \"1 किलो\"।",
        "fit_ok": " {qty} के लिए {label} {n} मिल जाएगा।",
        "fit_short": " {qty} के लिए {label} में इतना स्टॉक नहीं है (सिर्फ़ {avail} उपलब्ध)।",
    },
    "marathi": {
        "one": "हो, {label} उपलब्ध आहे.", "many": "हो, {word} मध्ये हे उपलब्ध आहेत: {labels}.",
        "low": " (फक्त {n} शिल्लक)", "out": " (सध्या स्टॉकमध्ये नाही)",
        "none_in_stock": "{labels} सध्या स्टॉकमध्ये नाही.", "subs": " हे उपलब्ध आहेत: {labels}.",
        "hint": "ऑर्डरमध्ये जोडायचे असेल तर सांगा, उदा. \"1 किलो\".",
        "fit_ok": " {qty} साठी {label} {n} मिळेल.",
        "fit_short": " {qty} साठी {label} चा इतका साठा नाही (फक्त {avail} उपलब्ध).",
    },
    "english": {
        "one": "Yes, {label} is available.", "many": "Yes, for {word} we have: {labels}.",
        "low": " (only {n} left)", "out": " (out of stock)",
        "none_in_stock": "{labels} is out of stock right now.", "subs": " Available instead: {labels}.",
        "hint": "Tell me the quantity if you want to add it, e.g. \"1 kg\".",
        "fit_ok": " For {qty}: {label} {n}.",
        "fit_short": " For {qty}, {label} does not have that much (only {avail} available).",
    },
}


def availability_reply(lang: str, entries: list[dict]) -> str:
    """Answer "is X available?" from database facts only. Each entry:
    {word, products: [{label, in_stock: bool, low: bool, left}], substitutes: [label]}."""
    t = _AVAIL[lang]
    parts: list[str] = []
    for e in entries:
        prods = e["products"]
        if not prods:
            parts.append(item_question(lang, e["word"], "unmatched", None, [], None))
            continue
        in_stock = [p for p in prods if p["in_stock"]]
        if not in_stock:
            parts.append(t["none_in_stock"].format(labels=_join([p["label"] for p in prods], lang)))
            if e["substitutes"]:
                parts[-1] += t["subs"].format(labels=_join(e["substitutes"], lang))
            continue

        def show(p: dict) -> str:
            return p["label"] + (t["low"].format(n=p["left"]) if p["low"] else "")

        if len(prods) == 1:
            parts.append(t["one"].format(label=show(prods[0])))
        else:
            labels = [show(p) if p["in_stock"] else p["label"] + t["out"] for p in prods]
            parts.append(t["many"].format(word=e["word"], labels=", ".join(labels)))
        fit = e.get("fit")
        if fit and parts:
            key = "fit_ok" if fit["ok"] else "fit_short"
            parts[-1] += " " + " ".join(t[key].format(qty=fit["qty"], label=fit["label"], n=fit["n"],
                                                      avail=fit.get("avail", "")).split())
    return " ".join(parts + [t["hint"]])
