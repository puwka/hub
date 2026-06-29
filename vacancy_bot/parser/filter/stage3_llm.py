"""Этап 3: LLM-классификация и извлечение структуры."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from config import config
from parser.filter.models import LLMClassification, VacancyExtract
from parser.filter.stage2_rules import extract_fields_rules, rule_based_vacancy_fallback

logger = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Ты классификатор Telegram сообщений.

Определи является ли сообщение вакансией.

Верни JSON:

{
  "is_vacancy": true/false,
  "confidence": 0-100,
  "reason": "короткая причина",
  "category": "vacancy|resume|ad|discussion|news|other"
}

Правила:

VACANCY:
- есть работодатель
- есть требования
- есть обязанности
- есть условия
- есть стек технологий

NOT VACANCY:
- поиск работы
- резюме
- курсы
- реклама
- новости
- обсуждения
- мемы
- вакансии агрегаторов без описания

Если сомневаешься:
is_vacancy = false"""

EXTRACT_PROMPT = """Извлеки структуру вакансии из текста. Верни только JSON:

{
  "title": "",
  "company": "",
  "salary": "",
  "employment": "",
  "location": "",
  "stack": [],
  "contacts": [],
  "remote": true,
  "text": ""
}

Если поле неизвестно — пустая строка или пустой массив. remote — boolean."""


def _parse_json_response(content: str) -> Optional[Dict[str, Any]]:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


async def _call_llm(system: str, user_text: str) -> Optional[str]:
    if not config.llm.enabled or not config.llm.api_key:
        return None

    url = f"{config.llm.base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.llm.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.llm.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text[:4000]},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=config.llm.timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning("LLM request failed: %s", e)
        return None


def _vacancy_from_dict(data: Dict[str, Any], fallback_text: str) -> VacancyExtract:
    return VacancyExtract(
        title=str(data.get("title") or "")[:500],
        company=str(data.get("company") or "")[:255],
        salary=str(data.get("salary") or "")[:255],
        employment=str(data.get("employment") or "")[:100],
        location=str(data.get("location") or "")[:255],
        stack=[str(s) for s in (data.get("stack") or [])][:20],
        contacts=[str(c) for c in (data.get("contacts") or [])][:10],
        remote=bool(data.get("remote", False)),
        text=str(data.get("text") or fallback_text),
    )


async def classify_message(text: str) -> LLMClassification:
    """Классификация через LLM или rule-based fallback."""
    raw = await _call_llm(CLASSIFY_PROMPT, text)
    if raw:
        data = _parse_json_response(raw)
        if data:
            return LLMClassification(
                is_vacancy=bool(data.get("is_vacancy")),
                confidence=int(data.get("confidence") or 0),
                reason=str(data.get("reason") or ""),
                category=str(data.get("category") or "other"),
                used_llm=True,
            )

    is_vac, conf, reason = rule_based_vacancy_fallback(text)
    return LLMClassification(
        is_vacancy=is_vac,
        confidence=conf,
        reason=reason,
        category="vacancy" if is_vac else "other",
        used_llm=False,
    )


async def extract_vacancy(text: str, classification: LLMClassification) -> VacancyExtract:
    """Извлечение полей через LLM или эвристики."""
    if classification.used_llm and config.llm.extract_enabled:
        raw = await _call_llm(EXTRACT_PROMPT, text)
        if raw:
            data = _parse_json_response(raw)
            if data:
                return _vacancy_from_dict(data, text)

    return extract_fields_rules(text)


async def get_embedding(text: str) -> Optional[list[float]]:
    """OpenAI-compatible embeddings для dedup."""
    if not config.llm.enabled or not config.llm.api_key or not config.llm.embedding_model:
        return None

    url = f"{config.llm.base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {config.llm.api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.llm.embedding_model,
        "input": text[:8000],
    }
    try:
        async with httpx.AsyncClient(timeout=config.llm.timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]
    except Exception as e:
        logger.debug("Embedding request failed: %s", e)
        return None
