"""Модели данных для многоступенчатой фильтрации вакансий."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class RawMessage:
    """Сырое сообщение из Telegram."""

    text: str
    message_id: int
    chat_id: str
    source: str
    source_title: str = ""
    date: Optional[datetime] = None
    has_photo: bool = False
    photo_message_id: Optional[int] = None
    is_forward: bool = False
    forward_text: str = ""


@dataclass
class VacancyExtract:
    """Структурированные поля вакансии."""

    title: str = ""
    company: str = ""
    salary: str = ""
    employment: str = ""
    location: str = ""
    stack: List[str] = field(default_factory=list)
    contacts: List[str] = field(default_factory=list)
    remote: bool = False
    text: str = ""


@dataclass
class LLMClassification:
    """Результат AI-классификации."""

    is_vacancy: bool = False
    confidence: int = 0
    reason: str = ""
    category: str = "other"
    extract: Optional[VacancyExtract] = None
    used_llm: bool = False


@dataclass
class FilterDecision:
    """Итог обработки сообщения."""

    decision: str  # saved | rejected
    stage: str
    reason: str
    confidence: Optional[int] = None
    category: str = "other"
    quality_score: int = 0
    cleaned_text: str = ""
    original_text: str = ""
    extract: Optional[VacancyExtract] = None
    simhash: Optional[str] = None
    text_hash: Optional[str] = None
    llm_used: bool = False
    duplicate_of: Optional[int] = None
    embedding: Optional[List[float]] = None

    def to_log_dict(self, message: RawMessage) -> Dict[str, Any]:
        return {
            "message_id": message.message_id,
            "chat_id": message.chat_id,
            "source": message.source,
            "decision": self.decision,
            "stage": self.stage,
            "reason": self.reason,
            "confidence": self.confidence,
            "category": self.category,
            "quality_score": self.quality_score,
        }
