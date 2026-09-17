"""Tests focus on the parts that must be defensible in a review: the score is
reproducible, absent signals lower confidence rather than the score, the buy/sell
inversion actually inverts, dedupe merges what it should, and learning stays
bounded."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.dedupe import dedupe  # noqa: E402
from app.core.features import build_features  # noqa: E402
from app.core.ingest import detect_mapping, parse_rows  # noqa: E402
from app.core.learning import learn_weights  # noqa: E402
from app.core.monitor import diff_snapshots  # noqa: E402
from app.core.normalize import (  # noqa: E402
    normalize_domain, normalize_name, normalize_phone, parse_revenue,
)
from app.core.scanner import parse_pages  # noqa: E402
from app.core.scoring import BUY, DEFAULT_WEIGHTS, SELL, band_fit, peak_fit, score_lead  # noqa: E402
from app.core.validate import validate_email  # noqa: E402

TARGETING = {
    "target_industries": ["hvac", "plumbing"],
    "adjacent_industries": ["construction"],
    "employee_band": [10, 100],
    "employee_peak": 28,
    "revenue_band": [2_000_000, 20_000_000],
    "regions": ["united states"],
}

NEGLECTED_SITE = {
    "status": "ok", "https": False, "copyright_year": 2018, "since_year": 1994,
    "tech": ["wordpress"], "markers": ["family_owned", "recurring_revenue"],
    "socials": ["facebook"], "has_careers": False, "has_blog": False,
    "has_cart": False, "phones": ["+15125550101"],
}

MODERN_SITE = {
    "status": "ok", "https": True, "copyright_year": 2026, "since_year": 2016,
    "tech": ["react", "google_analytics", "hubspot"], "markers": ["booking"],
    "socials": ["linkedin", "facebook", "instagram"], "has_careers": True,
    "has_blog": True, "has_cart": True, "phones": ["+15125550102"],
}

OLD_CO = {
    "company_name": "Delgado HVAC", "normalized_name": "delgado hvac",
    "normalized_domain": "delgadohvac.com", "country": "United States",
    "city": "Austin", "industry": "hvac", "employee_count": 26,
    "revenue_estimate": 4_200_000, "year_founded": 1994,
    "owner_name": "Maria Delgado", "email": "maria@delgadohvac.com",
    "email_status": "valid", "phone": "+15125550101", "linkedin_url": None,
}

NEW_CO = {
    **OLD_CO, "company_name": "Summit HVAC", "normalized_name": "summit hvac",
    "normalized_domain": "summithvac.com", "year_founded": 2016,
    "owner_name": "James Renner", "employee_count": 26,
}


# --------------------------------------------------------------------------- #
# normalizers
# --------------------------------------------------------------------------- #

def test_domain_normalization():
    assert normalize_domain("HTTPS://WWW.Example.com/path?a=1") == "example.com"
    assert normalize_domain("example.com:8080") == "example.com"
    assert normalize_domain("not a domain") is None


def test_name_normalization_strips_legal_suffix():
    assert normalize_name("Delgado HVAC, LLC") == "delgado hvac"
    assert normalize_name("Delgado HVAC Inc.") == "delgado hvac"


def test_revenue_parsing_handles_every_spelling():
    for raw in ["4200000", "$4.2M", "4.20 million", "4,200,000", "$4,200,000"]:
        assert abs(parse_revenue(raw) - 4_200_000) < 10_000


def test_phone_normalization():
    assert normalize_phone("(512) 555-0101") == "+15125550101"
    assert normalize_phone("+44 20 7946 0000") == "+442079460000"
    assert normalize_phone("nope") is None


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #

def test_role_accounts_are_risky_not_invalid():
    status, _ = validate_email("info@delgadohvac.com", check_mx=False)
    assert status == "risky"


def test_malformed_and_disposable_are_invalid():
    assert validate_email("contact@nodomain", check_mx=False)[0] == "invalid"
    assert validate_email("a@mailinator.com", check_mx=False)[0] == "invalid"


# --------------------------------------------------------------------------- #
# normalizer curves
# --------------------------------------------------------------------------- #

def test_band_fit_is_flat_inside_and_decays_outside():
    assert band_fit(50, 10, 100) == 1.0
    assert 0 < band_fit(140, 10, 100) < 1.0
    assert band_fit(140, 10, 100) > band_fit(400, 10, 100)
    assert band_fit(None, 10, 100) is None


def test_peak_fit_peaks_at_the_peak():
    assert peak_fit(28, 28, 10, 100) > peak_fit(60, 28, 10, 100)
    assert peak_fit(60, 28, 10, 100) > peak_fit(300, 28, 10, 100)


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #

def _score(lead, scan, mode):
    return score_lead(build_features(lead, scan), mode=mode,
                      weights=DEFAULT_WEIGHTS[mode], targeting=TARGETING)


def test_scoring_is_deterministic():
    a = _score(OLD_CO, NEGLECTED_SITE, BUY)
    b = _score(OLD_CO, NEGLECTED_SITE, BUY)
    assert a.score == b.score and a.confidence == b.confidence


def test_buy_and_sell_modes_disagree_about_a_neglected_site():
    """The core product claim: the same company is a strong acquisition target
    and a weak sales prospect, and the engine has to say so."""
    buy = _score(OLD_CO, NEGLECTED_SITE, BUY)
    sell = _score(OLD_CO, NEGLECTED_SITE, SELL)
    assert buy.score > sell.score

    buy_modern = _score(NEW_CO, MODERN_SITE, BUY)
    sell_modern = _score(NEW_CO, MODERN_SITE, SELL)
    assert sell_modern.score > buy_modern.score

    # and the inversion is specifically the modernization dimension
    assert buy.dimension_scores["modernization_upside"] > \
        buy_modern.dimension_scores["modernization_upside"]


def test_missing_data_lowers_confidence_not_score():
    thin = {k: v for k, v in OLD_CO.items()
            if k not in ("employee_count", "revenue_estimate", "phone", "email", "email_status")}
    full = _score(OLD_CO, NEGLECTED_SITE, BUY)
    sparse = _score(thin, NEGLECTED_SITE, BUY)
    assert sparse.confidence < full.confidence
    # a thin record is not dragged to the floor purely for being thin
    assert sparse.score > full.score * 0.5


def test_unreachable_site_is_not_treated_as_upside():
    dead = _score(OLD_CO, {"status": "unreachable"}, BUY)
    alive = _score(OLD_CO, NEGLECTED_SITE, BUY)
    assert dead.score < alive.score
    assert dead.dimension_scores["modernization_upside"] == 0.0


def test_quadrant_separates_score_from_confidence():
    strong = _score(OLD_CO, NEGLECTED_SITE, BUY)
    assert strong.quadrant in ("act", "verify")
    unscanned = _score(OLD_CO, {}, BUY)
    assert unscanned.confidence < strong.confidence


def test_contributions_sum_to_the_score():
    result = _score(OLD_CO, NEGLECTED_SITE, BUY)
    total = sum(c.contribution for c in result.contributions)
    assert abs(total - result.score) < 0.5


def test_pe_backed_marker_kills_succession_score():
    with_pe = dict(NEGLECTED_SITE)
    with_pe["markers"] = ["pe_backed"]
    clean = _score(OLD_CO, NEGLECTED_SITE, BUY)
    backed = _score(OLD_CO, with_pe, BUY)
    assert backed.dimension_scores["succession"] < clean.dimension_scores["succession"]


# --------------------------------------------------------------------------- #
# ingest + dedupe
# --------------------------------------------------------------------------- #

CSV = """Company Name,Website,Industry,City,Country,Employees,Annual Revenue,Owner,Email,Phone,Notes
Delgado HVAC LLC,https://www.delgadohvac.com,HVAC,Austin,United States,26,$4.2M,Maria Delgado,maria@delgadohvac.com,(512) 555-0101,from directory
DELGADO HVAC,,HVAC,Austin,United States,,,,,,dupe row
Summit Plumbing Inc,summitplumbing.com,Plumbing,Dallas,United States,10-20,2.5 million,James Renner,info@summitplumbing.com,,
"""


def test_column_mapping_prefers_exact_match():
    mapping = detect_mapping(["Company Name", "Website", "Annual Revenue", "Notes"])
    assert mapping["Company Name"] == "company_name"
    assert mapping["Website"] == "domain"
    assert mapping["Annual Revenue"] == "revenue_estimate"
    assert "Notes" not in mapping


def test_parse_and_dedupe_merges_the_duplicate():
    rows, report = parse_rows(CSV, check_mx=False)
    assert len(rows) == 3
    assert "Notes" in rows[0]["passthrough"]
    deduped, dd = dedupe(rows)
    assert len(deduped) == 2
    assert dd.exact_merges + dd.fuzzy_merges == 1
    delgado = next(r for r in deduped if "delgado" in r["normalized_name"])
    assert delgado["employee_count"] == 26  # the richer row's value survived


def test_domain_is_derived_from_email_when_absent():
    rows, _ = parse_rows(
        "Company Name,Email\nNo Site Co,owner@nositeco.com\n", check_mx=False)
    assert rows[0]["normalized_domain"] == "nositeco.com"


# --------------------------------------------------------------------------- #
# scanner parsing
# --------------------------------------------------------------------------- #

HTML = """<html><head><title>Delgado HVAC</title>
<meta name="description" content="Family owned since 1994"></head>
<body><p>&copy; 2018 Delgado HVAC. Family owned and operated.</p>
<a href="mailto:info@delgadohvac.com">email</a>
<a href="tel:+15125550101">call</a>
<a href="https://facebook.com/delgado">fb</a>
<script src="/wp-content/themes/x.js"></script>
<p>Ask about our maintenance plan.</p></body></html>"""


def test_scanner_extracts_signals_without_network():
    payload = parse_pages([("https://delgadohvac.com/", HTML)],
                          final_url="https://delgadohvac.com/", https=True, response_ms=210)
    assert payload["copyright_year"] == 2018
    assert payload["since_year"] == 1994
    assert "wordpress" in payload["tech"]
    assert "family_owned" in payload["markers"]
    assert "recurring_revenue" in payload["markers"]
    assert "facebook" in payload["socials"]
    assert payload["has_careers"] is False


# --------------------------------------------------------------------------- #
# monitor
# --------------------------------------------------------------------------- #

def test_diff_detects_the_changes_that_matter():
    old = {"status": "ok", "markers": [], "tech": ["wordpress"], "has_careers": False,
           "copyright_year": 2019}
    new = {"status": "ok", "markers": ["pe_backed"], "tech": ["wordpress", "react"],
           "has_careers": True, "copyright_year": 2026}
    kinds = {c.kind for c in diff_snapshots(old, new)}
    assert "pe_backed_appeared" in kinds
    assert "site_relaunched" in kinds
    assert "has_careers_appeared" in kinds
    assert "site_refreshed" in kinds


# --------------------------------------------------------------------------- #
# learning
# --------------------------------------------------------------------------- #

def test_learning_is_gated_on_sample_size():
    result = learn_weights([("accepted", {"succession": 0.9})] * 3, mode=BUY)
    assert result.eligible is False


def test_learning_shifts_weight_toward_the_discriminating_dimension():
    decisions = []
    for _ in range(12):
        decisions.append(("accepted", {"size_durability": 0.5, "succession": 0.9,
                                       "modernization_upside": 0.5,
                                       "market_position": 0.5, "data_confidence": 0.5}))
        decisions.append(("rejected", {"size_durability": 0.5, "succession": 0.1,
                                       "modernization_upside": 0.5,
                                       "market_position": 0.5, "data_confidence": 0.5}))
    result = learn_weights(decisions, mode=BUY)
    assert result.eligible
    assert result.weights["succession"] > DEFAULT_WEIGHTS[BUY]["succession"]
    assert abs(sum(result.weights.values()) - 1.0) < 1e-6
    # bounded: one pass cannot hand everything to a single dimension
    assert result.weights["succession"] < 0.75
