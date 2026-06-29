"""Скоринг качества вакансии."""

from __future__ import annotations

import re

from config import WHITELIST_KEYWORDS
from parser.filter.models import VacancyExtract
from parser.filter.stage2_rules import has_whitelist_keyword


def calculate_quality_score(text: str, extract: VacancyExtract) -> int:
    """
    Формула:
    +20 зарплата, +20 компания, +20 стек, +20 контакты, +20 длина > 500
    """
    score = 0

    if extract.salary or re.search(
        r"\d[\d\s]*(?:₽|руб|\$|usd)|зарплат|оплат|бюджет|rate",
        text,
        re.I,
    ):
        score += 20

    if extract.company or re.search(
        r"компани|стартап|agency|агентств|studio|студия|product",
        text,
        re.I,
    ):
        score += 20

    if extract.stack or re.search(
        r"python|react|vue|flutter|devops|backend|frontend|qa|data|ml|llm|gpt",
        text,
        re.I,
    ):
        score += 20

    if extract.contacts or re.search(r"@[\w]{3,}|t\.me/|\+?\d{10,}|\S+@\S+\.\S+", text):
        score += 20

    if len(text) > 500:
        score += 20

    if has_whitelist_keyword(text):
        score = min(100, score + 5)

    return min(100, score)
