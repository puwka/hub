"""Детектор дублей: hash, SimHash, embedding similarity."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import List, Optional, Tuple

from config import config
from parser.filter.text_cleaner import clean_for_dedup

logger = logging.getLogger(__name__)

SIMHASH_BITS = 64


def text_hash(text: str) -> str:
    normalized = clean_for_dedup(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def simhash(text: str) -> int:
    tokens = clean_for_dedup(text).split()
    if not tokens:
        return 0

    v = [0] * SIMHASH_BITS
    for token in tokens:
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(SIMHASH_BITS):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(SIMHASH_BITS):
        if v[i] >= 0:
            fingerprint |= 1 << i
    return fingerprint


def simhash_hex(text: str) -> str:
    return f"{simhash(text):016x}"


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def simhash_similarity(a: int, b: int) -> float:
    dist = hamming_distance(a, b)
    return 1.0 - dist / SIMHASH_BITS


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class DuplicateChecker:
    """Проверка дублей с кешем недавних вакансий."""

    def __init__(self):
        self._simhash_cache: List[Tuple[int, int]] = []  # (vacancy_id, simhash)
        self._embedding_cache: List[Tuple[int, List[float]]] = []

    async def load_recent(self, db) -> None:
        rows = await db.get_recent_vacancy_fingerprints(
            limit=config.filter.dedup_lookback_count,
            days=config.filter.dedup_lookback_days,
        )
        self._simhash_cache = []
        self._embedding_cache = []
        for row in rows:
            vid = row.get("id")
            sh = row.get("simhash")
            if vid and sh:
                try:
                    self._simhash_cache.append((vid, int(sh, 16)))
                except ValueError:
                    pass
            emb = row.get("embedding")
            if vid and emb and isinstance(emb, list):
                self._embedding_cache.append((vid, emb))

    def check_exact_hash(self, text: str, db_exists: bool) -> Optional[str]:
        if db_exists:
            return "exact_hash"
        return None

    def check_simhash(self, text: str) -> Optional[int]:
        sh = simhash(text)
        threshold = config.filter.simhash_similarity_threshold
        for vid, cached in self._simhash_cache:
            if simhash_similarity(sh, cached) >= threshold:
                return vid
        return None

    def check_embedding(self, embedding: List[float]) -> Optional[int]:
        threshold = config.filter.embedding_similarity_threshold
        for vid, cached in self._embedding_cache:
            if cosine_similarity(embedding, cached) >= threshold:
                return vid
        return None

    def register(self, vacancy_id: int, text: str, embedding: Optional[List[float]] = None) -> None:
        self._simhash_cache.insert(0, (vacancy_id, simhash(text)))
        if embedding:
            self._embedding_cache.insert(0, (vacancy_id, embedding))
        max_cache = config.filter.dedup_lookback_count
        self._simhash_cache = self._simhash_cache[:max_cache]
        self._embedding_cache = self._embedding_cache[:max_cache]
