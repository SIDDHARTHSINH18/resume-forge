"""Near-duplicate detection for resume text.

Deterministic and dependency-free: word shingles + a MinHash-style signature
used as a cheap prefilter, then exact Jaccard similarity for candidates that
pass the prefilter. Nothing is ever deleted automatically — duplicates are
only flagged for human review.
"""

from __future__ import annotations

import hashlib
import re
from itertools import islice

SHINGLE_SIZE = 5
SIGNATURE_SIZE = 32
SIGNATURE_PREFILTER = 0.62
JACCARD_THRESHOLD = 0.85

_WORD_RE = re.compile(r"[a-z0-9]+")


def normalize_for_similarity(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def shingles(text: str, size: int = SHINGLE_SIZE) -> set[str]:
    words = normalize_for_similarity(text)
    if len(words) < size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def _hash64(value: str) -> int:
    digest = hashlib.blake2b(value.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def signature(text: str, size: int = SIGNATURE_SIZE) -> list[int]:
    """MinHash-style signature: the `size` smallest shingle hashes.

    Two documents with high Jaccard overlap share many minimal hashes, which
    makes this a good cheap prefilter.
    """
    shingle_set = shingles(text)
    if not shingle_set:
        return []
    hashes = sorted(_hash64(shingle) for shingle in shingle_set)
    return hashes[:size]


def signature_similarity(sig_a: list[int], sig_b: list[int]) -> float:
    if not sig_a or not sig_b:
        return 0.0
    return len(set(sig_a) & set(sig_b)) / min(len(sig_a), len(sig_b))


def jaccard(text_a: str, text_b: str) -> float:
    set_a, set_b = shingles(text_a), shingles(text_b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def is_likely_duplicate(text_a: str, text_b: str, sig_a: list[int], sig_b: list[int]) -> tuple[bool, float]:
    """Return (is_duplicate, similarity) using prefilter then exact check."""
    if signature_similarity(sig_a, sig_b) < SIGNATURE_PREFILTER:
        return False, 0.0
    score = jaccard(text_a, text_b)
    return score >= JACCARD_THRESHOLD, round(score, 3)


def first_shingles(text: str, limit: int = 5) -> list[str]:
    return list(islice(sorted(shingles(text)), limit))
