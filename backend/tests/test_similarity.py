"""Near-duplicate text detection."""

from __future__ import annotations

from app.similarity import is_likely_duplicate, jaccard, shingles, signature, signature_similarity

TEXT_A = """Aarav Patel Ahmedabad Python SQL Git React internship web development projects
student management system portfolio website certifications coursera education BCA university"""

TEXT_B = """Aarav Patel Ahmedabad Python SQL Git React internship web development projects
student management system portfolio website certifications coursera education BCA university extra line"""

TEXT_C = """Completely different resume about accounting and finance with tally and GST filings
conducted audits for a small firm and prepared balance sheets for clients regularly"""


def test_identical_text_is_a_duplicate():
    is_dup, score = is_likely_duplicate(TEXT_A, TEXT_A, signature(TEXT_A), signature(TEXT_A))
    assert is_dup is True
    assert score == 1.0


def test_near_identical_text_is_a_duplicate():
    is_dup, score = is_likely_duplicate(TEXT_A, TEXT_B, signature(TEXT_A), signature(TEXT_B))
    assert is_dup is True
    assert score >= 0.85


def test_different_text_is_not_a_duplicate():
    is_dup, _score = is_likely_duplicate(TEXT_A, TEXT_C, signature(TEXT_A), signature(TEXT_C))
    assert is_dup is False


def test_jaccard_bounds():
    assert jaccard(TEXT_A, TEXT_A) == 1.0
    assert jaccard(TEXT_A, TEXT_C) < 0.2
    assert jaccard("", TEXT_A) == 0.0


def test_signature_is_deterministic_and_compact():
    sig_a1 = signature(TEXT_A)
    sig_a2 = signature(TEXT_A)
    assert sig_a1 == sig_a2
    assert len(sig_a1) <= 32
    assert signature_similarity(sig_a1, sig_a1) == 1.0
    assert signature_similarity(sig_a1, []) == 0.0


def test_shingles_of_short_text():
    assert shingles("hello world") == {"hello world"}
    assert shingles("") == set()
