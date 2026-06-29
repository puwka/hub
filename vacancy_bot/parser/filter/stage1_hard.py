"""Этап 1: жёсткие правила отсева."""

from __future__ import annotations

import re

from config import config
from parser.filter.models import FilterDecision, RawMessage
from parser.filter.text_cleaner import clean_text, count_links

_LINK_ONLY_RE = re.compile(
    r"^(?:https?://\S+|t\.me/\S+|@\w+\s*)+$",
    re.IGNORECASE,
)


def check_stage1(message: RawMessage) -> FilterDecision | None:
    """
    Вернуть FilterDecision с decision=rejected или None если прошёл этап.
    """
    cleaned, original = clean_text(message.text or "")

    if message.has_photo and not cleaned.strip():
        return FilterDecision(
            decision="rejected",
            stage="stage1",
            reason="only_photo",
            original_text=original,
            cleaned_text=cleaned,
        )

    if message.is_forward and not cleaned.strip():
        return FilterDecision(
            decision="rejected",
            stage="stage1",
            reason="forward_without_text",
            original_text=original,
            cleaned_text=cleaned,
        )

    if len(cleaned) < config.filter.min_text_length:
        return FilterDecision(
            decision="rejected",
            stage="stage1",
            reason=f"too_short:{len(cleaned)}",
            original_text=original,
            cleaned_text=cleaned,
        )

    if _LINK_ONLY_RE.match(cleaned.strip()):
        return FilterDecision(
            decision="rejected",
            stage="stage1",
            reason="link_only",
            original_text=original,
            cleaned_text=cleaned,
        )

    links = count_links(original)
    if links > config.filter.max_links:
        return FilterDecision(
            decision="rejected",
            stage="stage1",
            reason=f"too_many_links:{links}",
            original_text=original,
            cleaned_text=cleaned,
        )

    return None
