"""Оркестратор многоступенчатой фильтрации."""

from __future__ import annotations

import logging
from typing import Optional

from config import config
from database import db
from parser.filter.category import detect_category
from parser.filter.dedup import DuplicateChecker, simhash_hex, text_hash
from parser.filter.models import FilterDecision, RawMessage, VacancyExtract
from parser.filter.scoring import calculate_quality_score
from parser.filter.stage1_hard import check_stage1
from parser.filter.stage2_rules import check_stage2
from parser.filter.stage3_llm import classify_message, extract_vacancy, get_embedding
from parser.filter.text_cleaner import clean_text

logger = logging.getLogger(__name__)


class VacancyFilterPipeline:
    """Многоступенчатая фильтрация сообщений."""

    def __init__(self):
        self.dedup = DuplicateChecker()
        self._dedup_loaded = False
        self._session_stats = {
            "received": 0,
            "saved": 0,
            "rejected": 0,
            "duplicates": 0,
        }

    async def ensure_dedup_cache(self) -> None:
        if not self._dedup_loaded:
            await self.dedup.load_recent(db)
            self._dedup_loaded = True

    @property
    def session_stats(self) -> dict:
        return dict(self._session_stats)

    async def process(self, message: RawMessage) -> FilterDecision:
        self._session_stats["received"] += 1
        await db.increment_parse_metrics(
            source=message.source,
            received=1,
            saved=0,
            rejected=0,
            duplicates=0,
        )

        # Этап 1
        stage1 = check_stage1(message)
        if stage1:
            return await self._reject(message, stage1)

        cleaned, original = clean_text(message.text or "")
        message_clean = RawMessage(
            text=cleaned,
            message_id=message.message_id,
            chat_id=message.chat_id,
            source=message.source,
            source_title=message.source_title,
            date=message.date,
            has_photo=message.has_photo,
            photo_message_id=message.photo_message_id,
            is_forward=message.is_forward,
        )

        # Этап 2
        stage2 = check_stage2(cleaned)
        if stage2:
            stage2.original_text = original
            return await self._reject(message, stage2)

        # Этап 3 — LLM / fallback
        classification = await classify_message(cleaned)
        min_conf = config.filter.min_llm_confidence if classification.used_llm else config.filter.min_rule_confidence

        if not classification.is_vacancy or classification.confidence < min_conf:
            return await self._reject(
                message,
                FilterDecision(
                    decision="rejected",
                    stage="stage3",
                    reason=f"not_vacancy:{classification.reason}",
                    confidence=classification.confidence,
                    cleaned_text=cleaned,
                    original_text=original,
                    llm_used=classification.used_llm,
                ),
            )

        await self.ensure_dedup_cache()
        th = text_hash(cleaned)

        if await db.vacancy_exists_by_hash(th):
            return await self._reject(
                message,
                FilterDecision(
                    decision="rejected",
                    stage="dedup",
                    reason="exact_hash",
                    cleaned_text=cleaned,
                    original_text=original,
                    text_hash=th,
                    llm_used=classification.used_llm,
                ),
                duplicate=True,
            )

        dup_id = self.dedup.check_simhash(cleaned)
        if dup_id:
            return await self._reject(
                message,
                FilterDecision(
                    decision="rejected",
                    stage="dedup",
                    reason=f"simhash_similar:{dup_id}",
                    cleaned_text=cleaned,
                    original_text=original,
                    duplicate_of=dup_id,
                    llm_used=classification.used_llm,
                ),
                duplicate=True,
            )

        embedding = await get_embedding(cleaned)
        if embedding:
            dup_emb = self.dedup.check_embedding(embedding)
            if dup_emb:
                return await self._reject(
                    message,
                    FilterDecision(
                        decision="rejected",
                        stage="dedup",
                        reason=f"embedding_similar:{dup_emb}",
                        cleaned_text=cleaned,
                        original_text=original,
                        duplicate_of=dup_emb,
                        llm_used=classification.used_llm,
                    ),
                    duplicate=True,
                )

        extract = await extract_vacancy(cleaned, classification)
        if not extract.text:
            extract.text = cleaned

        category = detect_category(cleaned)
        quality = calculate_quality_score(cleaned, extract)

        if quality < config.filter.min_quality_score:
            return await self._reject(
                message,
                FilterDecision(
                    decision="rejected",
                    stage="quality",
                    reason=f"low_quality:{quality}",
                    confidence=classification.confidence,
                    category=category,
                    quality_score=quality,
                    cleaned_text=cleaned,
                    original_text=original,
                    llm_used=classification.used_llm,
                ),
            )

        return FilterDecision(
            decision="saved",
            stage="saved",
            reason=classification.reason,
            confidence=classification.confidence,
            category=category,
            quality_score=quality,
            cleaned_text=cleaned,
            original_text=original,
            extract=extract,
            simhash=simhash_hex(cleaned),
            text_hash=th,
            llm_used=classification.used_llm,
            embedding=embedding,
        )

    async def _reject(
        self,
        message: RawMessage,
        decision: FilterDecision,
        duplicate: bool = False,
    ) -> FilterDecision:
        decision.decision = "rejected"
        self._session_stats["rejected"] += 1
        if duplicate:
            self._session_stats["duplicates"] += 1

        decision.original_text = decision.original_text or message.text
        await db.log_parse_filter(decision.to_log_dict(message))
        await db.increment_parse_metrics(
            source=message.source,
            received=0,
            saved=0,
            rejected=1,
            duplicates=1 if duplicate else 0,
        )
        logger.info(
            "FILTER reject [%s] %s: %s (msg %s)",
            decision.stage,
            message.source,
            decision.reason,
            message.message_id,
        )
        return decision

    async def log_saved(self, message: RawMessage, decision: FilterDecision, vacancy_id: int) -> None:
        self._session_stats["saved"] += 1
        await db.log_parse_filter(decision.to_log_dict(message))
        await db.increment_parse_metrics(
            source=message.source,
            received=0,
            saved=1,
            rejected=0,
            duplicates=0,
            quality_score=decision.quality_score,
        )
        if decision.simhash:
            self.dedup.register(
                vacancy_id,
                decision.cleaned_text,
                decision.embedding,
            )


pipeline = VacancyFilterPipeline()
