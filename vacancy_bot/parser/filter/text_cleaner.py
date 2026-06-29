"""Очистка текста сообщений."""

from __future__ import annotations

import re
import unicodedata


_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)

_HTML_RE = re.compile(r"<[^>]+>")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*|__([^_]+)__")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)|(?<!_)_([^_\n]+)_(?!_)")
_MENTION_RE = re.compile(r"@\w+")
_URL_RE = re.compile(r"https?://\S+|t\.me/\S+", re.IGNORECASE)
_TG_HASHTAG_LINK_RE = re.compile(
    r"\[\[\(tg://searchhashtag[^\)]+\)\s*\"[^\"]*\"|"
    r"\[#\]\(tg://search_hashtag[^\)]+\)|"
    r"\[#\]\(tg://searchhashtag[^\)]+\)|"
    r"tg://searchhashtag[^\s\)]+|"
    r"tg://search_hashtag[^\s\)]+",
    re.IGNORECASE,
)
_REPEAT_CHAR_RE = re.compile(r"(.)\1{3,}")
_TELEGRA_MD_RE = re.compile(
    r"\[[^\]]*\]\(https?://(?:www\.)?telegra\.ph[^\)]*\)",
    re.IGNORECASE,
)
_TELEGRA_URL_RE = re.compile(r"https?://(?:www\.)?telegra\.ph\S*", re.IGNORECASE)


def remove_telegra_links(text: str) -> str:
    """Удалить ссылки и markdown-вставки telegra.ph."""
    if not text:
        return text
    text = _TELEGRA_MD_RE.sub("", text)
    text = _TELEGRA_URL_RE.sub("", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text)


def clean_text(raw: str) -> tuple[str, str]:
    """
    Очистить текст для анализа.

    Returns:
        (cleaned_text, original_text)
    """
    original = raw or ""
    text = original

    text = _TG_HASHTAG_LINK_RE.sub("", text)
    text = remove_telegra_links(text)
    text = _HTML_RE.sub("", text)
    text = _MD_BOLD_RE.sub(r"\1\2", text)
    text = _MD_ITALIC_RE.sub(r"\1\2", text)
    text = unicodedata.normalize("NFKC", text)
    text = _REPEAT_CHAR_RE.sub(r"\1\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()

    return text, original


def clean_for_dedup(text: str) -> str:
    """Нормализация для хеширования и SimHash."""
    text = text.lower()
    text = _URL_RE.sub(" ", text)
    text = _MENTION_RE.sub(" ", text)
    text = strip_emoji(text)
    text = re.sub(r"[^\w\s+#]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def count_links(text: str) -> int:
    return len(_URL_RE.findall(text)) + len(re.findall(r"t\.me/\S+", text, re.I))
