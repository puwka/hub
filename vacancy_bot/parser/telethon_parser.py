"""
Telethon парсер для Telegram каналов и групп.
Использует user account для доступа к сообщениям.
Многоступенчатая фильтрация через parser.filter.pipeline.
"""

import re
import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, Message
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    ChatAdminRequiredError,
)

from config import config
from database import db
from utils.proxy import get_telethon_proxy
from parser.filter.text_cleaner import remove_telegra_links
from parser.filter.pipeline import pipeline
from parser.filter.models import RawMessage

logger = logging.getLogger(__name__)


class TelegramParser:
    """
    Парсер Telegram каналов и групп через Telethon.
    Бот НЕ добавляется в каналы - используется user session.
    """

    def __init__(self):
        self.client: Optional[TelegramClient] = None
        self.is_authorized = False

    async def start(self) -> bool:
        """Запуск Telethon клиента."""
        session_path = Path(f"{config.telethon.session_name}.session")
        if not session_path.exists():
            logger.warning(
                "⚠️ Telethon: нет файла %s — парсинг отключён. "
                "Авторизуйтесь: python auth_telethon.py",
                session_path.name,
            )
            self.is_authorized = False
            return False

        try:
            proxy = get_telethon_proxy()
            self.client = TelegramClient(
                config.telethon.session_name,
                config.telethon.api_id,
                config.telethon.api_hash,
                proxy=proxy,
            )

            await asyncio.wait_for(self.client.connect(), timeout=15)
            self.is_authorized = await self.client.is_user_authorized()

            if self.is_authorized:
                me = await self.client.get_me()
                logger.info(
                    "✅ Telethon авторизован как: %s (@%s)",
                    me.first_name,
                    me.username,
                )
                return True

            logger.error(
                "❌ Telethon session недействителен. Запустите: python auth_telethon.py"
            )
            return False

        except asyncio.TimeoutError:
            logger.error(
                "Telethon: таймаут подключения. Проверьте VPN и PROXY_URL в .env"
            )
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telethon: {e}")
            return False

    async def stop(self) -> None:
        if self.client:
            await self.client.disconnect()
            logger.info("Telethon отключен")

    def _format_display_text(self, text: str) -> str:
        """Markdown → HTML для рассылки."""
        text = remove_telegra_links(text or "")
        text = re.sub(r"\*\*([^*\n]+(?:\*[^*\n]+)*)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__([^_\n]+(?:_[^_\n]+)*)__", r"<b>\1</b>", text)
        text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<i>\1</i>", text)
        return text.strip()

    async def _enrich_contacts(self, text: str, message: Message, source_id: str) -> str:
        """Добавить контакт автора поста (не канала-источника)."""
        original = message.text or text
        has_contact = bool(
            re.search(r"@[\w]+", original)
            or re.search(
                r"(\+?\d{1,3}[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
                original,
            )
            or re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", original)
        )
        if has_contact:
            return text

        author_username = None
        try:
            if message.from_id:
                sender = await message.get_sender()
                if sender:
                    username = getattr(sender, "username", None)
                    if username:
                        candidate = f"@{username}"
                        if not self._is_source_username(candidate, source_id):
                            author_username = candidate
        except Exception as e:
            logger.debug("Не удалось получить username автора: %s", e)

        if author_username:
            return f"{text}\n\nКонтакты для отклика: {author_username}"
        return text

    @staticmethod
    def _is_source_username(username: str, source_id: str) -> bool:
        u = username.lower().lstrip("@")
        s = source_id.lower().lstrip("@").replace("https://t.me/", "")
        return bool(u and s and u == s)

    async def parse_source(
        self,
        source_id: str,
        source_type: str,
        last_message_id: int = 0,
        limit: int = 100,
    ) -> List[Dict]:
        """Парсинг одного источника через многоступенчатый фильтр."""
        vacancies = []

        if not self.is_authorized:
            logger.warning("Telethon не авторизован, парсинг невозможен")
            return vacancies

        try:
            entity = await self.client.get_entity(source_id)
            entity_title = getattr(entity, "title", source_id)
            chat_id = str(getattr(entity, "id", source_id))

            logger.info(f"📡 Парсинг: {entity_title} ({source_id})")

            messages: List[Message] = await self.client.get_messages(
                entity,
                limit=limit,
                min_id=last_message_id,
            )

            max_message_id = last_message_id
            processed = 0
            found = 0

            for message in messages:
                processed += 1
                max_message_id = max(max_message_id, message.id)

                has_photo = False
                if message.media:
                    try:
                        from telethon.tl.types import MessageMediaPhoto
                        if isinstance(message.media, MessageMediaPhoto):
                            has_photo = True
                    except Exception:
                        pass

                text = message.text or ""
                is_forward = bool(getattr(message, "fwd_from", None))

                if not text and not has_photo and not is_forward:
                    continue

                raw = RawMessage(
                    text=text,
                    message_id=message.id,
                    chat_id=chat_id,
                    source=source_id,
                    source_title=entity_title,
                    date=message.date,
                    has_photo=has_photo,
                    photo_message_id=message.id if has_photo else None,
                    is_forward=is_forward,
                )

                decision = await pipeline.process(raw)
                if decision.decision != "saved" or not decision.extract:
                    continue

                display_text = self._format_display_text(decision.original_text or text)
                display_text = await self._enrich_contacts(display_text, message, source_id)

                extract = decision.extract
                if not display_text.strip():
                    display_text = self._format_display_text(text)

                vacancy = {
                    "text": display_text,
                    "original_text": decision.original_text or text,
                    "category": decision.category,
                    "source": source_id,
                    "source_message_id": message.id,
                    "source_title": entity_title,
                    "date": message.date,
                    "has_photo": False,
                    "photo_message_id": None,
                    "title": extract.title,
                    "company": extract.company,
                    "salary": extract.salary,
                    "employment": extract.employment,
                    "location": extract.location,
                    "stack": extract.stack,
                    "contacts": extract.contacts,
                    "remote": extract.remote,
                    "quality_score": decision.quality_score,
                    "simhash": decision.simhash,
                    "text_hash": decision.text_hash,
                    "filter_confidence": decision.confidence,
                    "filter_reason": decision.reason,
                    "embedding": decision.embedding,
                    "_raw_message": raw,
                    "_filter_decision": decision,
                }

                vacancies.append(vacancy)
                found += 1
                logger.info(
                    "✅ Вакансия [%s] quality=%s conf=%s: %s",
                    decision.category,
                    decision.quality_score,
                    decision.confidence,
                    (extract.title or display_text[:80]),
                )

            if max_message_id > last_message_id:
                await db.update_source_last_message(source_id, max_message_id)

            stats = pipeline.session_stats
            logger.info(
                f"✅ {entity_title}: сообщений {processed}, "
                f"сохранено {found}, отклонено {stats.get('rejected', 0)}, "
                f"дублей {stats.get('duplicates', 0)}"
            )

        except ChannelPrivateError:
            logger.warning(f"⚠️ Канал {source_id} приватный или недоступен")
        except ChatAdminRequiredError:
            logger.warning(f"⚠️ Требуются права админа для {source_id}")
        except FloodWaitError as e:
            logger.warning(f"⏳ FloodWait: ждем {e.seconds} секунд")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга {source_id}: {e}")

        return vacancies

    async def parse_all_sources(self) -> Tuple[int, int]:
        """Парсинг всех активных источников."""
        if not self.is_authorized:
            logger.warning("Telethon не авторизован")
            return 0, 0

        sources = await db.get_active_sources()
        if not sources:
            logger.info("Нет активных источников для парсинга")
            return 0, 0

        pipeline._session_stats = {
            "received": 0,
            "saved": 0,
            "rejected": 0,
            "duplicates": 0,
        }
        pipeline._dedup_loaded = False

        total_vacancies = 0
        processed_sources = 0

        for source in sources:
            try:
                vacancies = await self.parse_source(
                    source_id=source["source_id"],
                    source_type=source["source_type"],
                    last_message_id=source.get("last_message_id", 0),
                    limit=config.parser.max_vacancies_per_parse,
                )

                for vacancy in vacancies:
                    decision = vacancy.pop("_filter_decision", None)
                    raw = vacancy.pop("_raw_message", None)
                    embedding = vacancy.pop("embedding", None)
                    text_hash = vacancy.pop("text_hash", None)

                    result = await db.create_vacancy(
                        text=vacancy["text"],
                        category=vacancy["category"],
                        source=vacancy["source"],
                        source_message_id=vacancy["source_message_id"],
                        has_photo=vacancy.get("has_photo", False),
                        photo_message_id=vacancy.get("photo_message_id"),
                        original_text=vacancy.get("original_text"),
                        title=vacancy.get("title"),
                        company=vacancy.get("company"),
                        salary=vacancy.get("salary"),
                        employment=vacancy.get("employment"),
                        location=vacancy.get("location"),
                        stack=vacancy.get("stack"),
                        contacts=vacancy.get("contacts"),
                        remote=vacancy.get("remote"),
                        quality_score=vacancy.get("quality_score", 0),
                        simhash=vacancy.get("simhash"),
                        embedding=embedding,
                        filter_confidence=vacancy.get("filter_confidence"),
                        filter_reason=vacancy.get("filter_reason"),
                        text_hash=text_hash,
                    )

                    if result and decision and raw:
                        await pipeline.log_saved(raw, decision, result["id"])

                total_vacancies += len(vacancies)
                processed_sources += 1
                await asyncio.sleep(2)

            except Exception as e:
                logger.error(f"Ошибка обработки источника {source['source_id']}: {e}")

        stats = pipeline.session_stats
        logger.info(
            f"📊 Парсинг завершен: {processed_sources} источников, "
            f"{total_vacancies} вакансий | получено {stats['received']}, "
            f"отклонено {stats['rejected']}, дублей {stats['duplicates']}"
        )

        return processed_sources, total_vacancies

    async def get_channel_info(self, source_id: str) -> Optional[Dict]:
        if not self.is_authorized:
            return None

        try:
            entity = await self.client.get_entity(source_id)
            return {
                "id": entity.id,
                "title": getattr(entity, "title", source_id),
                "username": getattr(entity, "username", None),
                "participants_count": getattr(entity, "participants_count", None),
                "is_channel": isinstance(entity, Channel),
                "is_group": isinstance(entity, Chat),
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о {source_id}: {e}")
            return None


parser = TelegramParser()
