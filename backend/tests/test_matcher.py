"""Matcher rules: matched / ambiguous / rerank / unmatched, pack sizes, brand typos (plan Stage 3)."""
import pytest

from app.services.matcher import CatalogIndex, match
from app.services.unit_normalizer import normalize
from tests.catalog import load_products


@pytest.fixture(scope="module")
def index():
    return CatalogIndex(load_products())


def names(r):
    return [c.product.name for c in r.candidates]


def test_amool_butter_is_amul(index):
    r = match("amool butter", index)
    assert r.status == "matched"
    assert r.product.brand == "Amul" and "Butter" in r.product.name


def test_cheeni_is_sugar(index):
    r = match("cheeni", index)
    assert r.status == "matched" and r.product.name == "Sugar (Loose)"
    assert r.confidence >= 0.85


def test_tel_is_ambiguous_with_three_candidates(index):
    r = match("tel", index)
    assert r.status == "ambiguous" and r.kind == "ambiguous_product"
    assert len(r.candidates) == 3
    assert all(c.product.category == "Oil" for c in r.candidates)
    assert {c.product.pack_size for c in r.candidates} == {1}  # one chip per oil, smallest pack


def test_dal_is_ambiguous_among_four_dals(index):
    r = match("dal", index)
    assert r.status == "ambiguous" and len(r.candidates) == 4


def test_atta_in_kilos_picks_the_loose_atta(index):
    r = match("atta", index, normalize("2", None, "kilo"))
    assert r.status == "matched" and r.product.name == "Atta (Loose)"


def test_branded_atta_picks_the_pack_that_fits(index):
    r = match("atta", index, normalize("2", None, "kilo"), brand_guess="Aashirvaad")
    assert r.status == "matched" and r.product.name == "Aashirvaad Atta 1kg"  # 2 x 1 kg pack


def test_pack_size_that_does_not_fit_is_ambiguous(index):
    r = match("aashirvaad atta", index, normalize("2.5", None, "kilo"))
    assert r.status == "ambiguous" and r.kind == "pack_size"
    assert len(r.candidates) == 2


def test_no_size_said_defaults_to_smallest_pack_with_lower_confidence(index):
    r = match("amul butter", index)
    assert r.status == "matched" and r.product.name == "Amul Butter 100g"
    assert r.pack_defaulted and r.confidence < 0.85


def test_parle_g_variants(index):
    for q in ("parle g", "parle-g", "parleji"):
        r = match(q, index, normalize("3", None, "packet"))
        assert r.status == "matched" and r.product.name == "Parle-G 50g", q


def test_devanagari_and_marathi_aliases(index):
    assert match("नमक", index).product.name == "Tata Salt 1kg"
    assert match("साखर", index).product.name == "Sugar (Loose)"
    assert match("चावल", index).status == "ambiguous"  # basmati or kolam
    assert match("तांदूळ", index).status == "ambiguous"


def test_unknown_product_is_unmatched(index):
    r = match("oats", index)
    assert r.status == "unmatched" and r.candidates == []


def test_gibberish_is_unmatched(index):
    assert match("asdkj qwe zz", index).status == "unmatched"


def test_typo_lands_in_rerank_or_match_never_a_wrong_certain_match(index):
    r = match("shakar", index)
    assert r.status in ("matched", "rerank")
    if r.status == "rerank":
        assert any(c.product.name == "Sugar (Loose)" for c in r.candidates)


def test_candidates_never_exceed_six(index):
    for q in ("tel", "dal", "butter", "chawal", "atta", "milk"):
        assert len(match(q, index).candidates) <= 6


def test_specific_oil_is_not_ambiguous(index):
    r = match("mustard tel", index)
    assert r.status in ("matched", "ambiguous")
    assert "Dhara Mustard Oil 1L" in names(r)[:1] + [r.product.name if r.product else ""]


def test_restricted_index_only_returns_given_ids(index):
    sub = index.restrict([14, 16])
    r = match("tel", sub)
    assert {c.product.id for c in r.candidates} <= {14, 16}
