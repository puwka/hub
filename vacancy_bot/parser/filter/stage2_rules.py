"""Этап 2: правила NOT_VACANCY, чёрный и белый списки."""

from __future__ import annotations

import re
from typing import Optional, Tuple

from config import (
    BLACKLIST_KEYWORDS,
    NOT_VACANCY_PHRASES,
    WHITELIST_KEYWORDS,
    VACANCY_STRONG_INDICATORS,
    VACANCY_CONDITIONS_INDICATORS,
    VACANCY_TASK_INDICATORS,
    VACANCY_ACTION_INDICATORS,
    RESUME_STRONG_INDICATORS,
    RESUME_START_PATTERNS,
)
from parser.filter.models import FilterDecision, VacancyExtract


def _match_phrase(text_lower: str, phrase: str) -> bool:
    if phrase.startswith("regex:"):
        return bool(re.search(phrase[6:], text_lower, re.IGNORECASE))
    return phrase.lower() in text_lower


def check_not_vacancy_phrases(text: str) -> Optional[str]:
    text_lower = text.lower()
    for phrase in NOT_VACANCY_PHRASES:
        if _match_phrase(text_lower, phrase):
            return phrase
    return None


def check_blacklist(text: str) -> Optional[str]:
    text_lower = text.lower()
    for word in BLACKLIST_KEYWORDS:
        if word.lower() in text_lower:
            return word
    return None


def has_whitelist_keyword(text: str) -> bool:
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in WHITELIST_KEYWORDS)


def check_stage2(text: str) -> Optional[FilterDecision]:
    """Вернуть rejection или None."""
    text_lower = text.lower()

    phrase = check_not_vacancy_phrases(text)
    if phrase:
        return FilterDecision(
            decision="rejected",
            stage="stage2",
            reason=f"not_vacancy_phrase:{phrase}",
            cleaned_text=text,
        )

    black = check_blacklist(text)
    if black:
        return FilterDecision(
            decision="rejected",
            stage="stage2",
            reason=f"blacklist:{black}",
            cleaned_text=text,
        )

    for pattern in RESUME_START_PATTERNS:
        if re.search(pattern, text_lower.strip()):
            if pattern == r"^ищу\s+":
                after = text_lower.strip()[4:].strip()
                resume_words = (
                    "работу", "проект", "команду", "компанию", "заказчика",
                    "клиента", "удаленку", "фриланс", "вакансию",
                )
                if any(after.startswith(w) for w in resume_words):
                    return FilterDecision(
                        decision="rejected",
                        stage="stage2",
                        reason="resume:ищу_работу/команду",
                        cleaned_text=text,
                    )
            else:
                return FilterDecision(
                    decision="rejected",
                    stage="stage2",
                    reason=f"resume_start:{pattern}",
                    cleaned_text=text,
                )

    for pattern in RESUME_STRONG_INDICATORS:
        if re.search(pattern, text_lower):
            return FilterDecision(
                decision="rejected",
                stage="stage2",
                reason="resume_strong",
                cleaned_text=text,
            )

    return None


def rule_based_vacancy_fallback(text: str) -> Tuple[bool, int, str]:
    """
    Fallback-классификация без LLM.
    Returns: (is_vacancy, confidence, reason)
    """
    text_lower = text.lower()
    strong = sum(1 for p in VACANCY_STRONG_INDICATORS if re.search(p, text_lower))
    conditions = sum(1 for p in VACANCY_CONDITIONS_INDICATORS if re.search(p, text_lower))
    tasks = sum(1 for p in VACANCY_TASK_INDICATORS if re.search(p, text_lower))
    actions = sum(1 for p in VACANCY_ACTION_INDICATORS if re.search(p, text_lower))
    total = strong + conditions + tasks + actions

    if re.search(r"#ищу\b", text_lower):
        return True, 75, "hashtag_ищу"

    if text_lower.strip().startswith("ищу "):
        after = text_lower.strip()[4:]
        if not any(after.startswith(w) for w in ("работу", "проект", "команду")):
            return True, 70, "ищу_специалиста"

    if strong >= 1 and (conditions >= 1 or tasks >= 1 or actions >= 1):
        return True, 65, "strong+details"
    if strong >= 2:
        return True, 60, "strong_indicators"
    if conditions >= 1 and tasks >= 1:
        return True, 55, "conditions+tasks"
    if total >= 3:
        return True, 50, "total_indicators"

    if has_whitelist_keyword(text):
        return True, 45, "whitelist_keyword"

    return False, 20, "insufficient_vacancy_signals"


def extract_fields_rules(text: str) -> VacancyExtract:
    """Эвристическое извлечение полей без LLM."""
    text_lower = text.lower()
    extract = VacancyExtract(text=text)

    salary_match = re.search(
        r"(\d[\d\s]{2,}[\d]?\s*(?:₽|руб|рублей|\$|usd|eur|€)|"
        r"от\s+\d+|до\s+\d+|зарплат[аы]\s*[:\-]?\s*\S+)",
        text,
        re.IGNORECASE,
    )
    if salary_match:
        extract.salary = salary_match.group(1).strip()

    company_match = re.search(
        r"(?:компани[яи]|employer|работодатель)[:\s\-]+([^\n]{2,80})",
        text,
        re.IGNORECASE,
    )
    if company_match:
        extract.company = company_match.group(1).strip()

    title_match = re.search(
        r"(?:#ищу|ищу|vacancy|вакансия)[:\s\-]*([^\n]{3,80})",
        text,
        re.IGNORECASE,
    )
    if title_match:
        extract.title = title_match.group(1).strip()
    elif text.strip():
        extract.title = text.strip().split("\n")[0][:120]

    extract.remote = bool(re.search(r"удален|remote|удалён", text_lower))
    extract.contacts = list(set(re.findall(r"@[\w]{3,}|\+?\d[\d\s\-()]{8,}|\S+@\S+\.\S+", text)))
    extract.stack = [
        kw for kw in WHITELIST_KEYWORDS
        if kw.lower() in text_lower and len(kw) > 2
    ][:15]

    if re.search(r"full.?time|полная\s+занятость", text_lower):
        extract.employment = "full-time"
    elif re.search(r"part.?time|частичн", text_lower):
        extract.employment = "part-time"
    elif re.search(r"проект|project|фриланс|freelance", text_lower):
        extract.employment = "project"

    loc = re.search(r"(?:локация|location|город)[:\s\-]+([^\n]{2,60})", text, re.I)
    if loc:
        extract.location = loc.group(1).strip()

    return extract
