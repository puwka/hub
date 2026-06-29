"""Определение категории вакансии."""

from __future__ import annotations

import logging
import re
from typing import Dict

from config import CATEGORIES

logger = logging.getLogger(__name__)

PRIORITY_PHRASES = {
    "it": [
        r"\b(программист|разработчик|developer|devops|backend|frontend|fullstack)\b",
        r"\b(python|javascript|java|react|node|php|golang|rust)\s+(разработчик|developer)\b",
        r"\b(веб|мобильн|ios|android)\s+разработк",
    ],
    "design": [
        r"\b(дизайнер|designer)\b",
        r"\b(ui|ux|графическ|веб)\s+дизайн",
    ],
    "marketing": [
        r"\b(маркетолог|marketer|smm|таргет|seo)\s+(специалист|менеджер)\b",
    ],
    "copywriting": [
        r"\b(копирайтер|copywriter|редактор|editor)\b",
    ],
    "video": [
        r"\b(монтажер|видеограф|video\s+editor|motion\s+design)\b",
    ],
    "ai_ml": [
        r"\b(ai|ml|machine\s+learning|data\s+science|llm|gpt|prompt)\b",
        r"\b(нейросет|искусственн\s+интеллект)\b",
    ],
}


def detect_category(text: str) -> str:
    text_lower = text.lower()
    scores: Dict[str, float] = {}

    for cat_id, phrases in PRIORITY_PHRASES.items():
        for phrase in phrases:
            if re.search(phrase, text_lower, re.IGNORECASE):
                scores[cat_id] = scores.get(cat_id, 0) + 5.0

    for cat_id, cat_data in CATEGORIES.items():
        if cat_id == "other":
            continue
        if cat_id in scores and scores[cat_id] >= 5.0:
            continue

        score = scores.get(cat_id, 0.0)
        for keyword in cat_data["keywords"]:
            kw = keyword.lower()
            pattern = r"\b" + re.escape(kw) + r"\b"
            if re.search(pattern, text_lower):
                score += 1.0 + len(kw) / 10.0
            elif kw in text_lower:
                score += 0.3

        if score > 0:
            scores[cat_id] = score

    if not scores:
        return "other"

    best = max(scores, key=scores.get)
    if scores[best] < 1.0:
        return "other"
    return best
