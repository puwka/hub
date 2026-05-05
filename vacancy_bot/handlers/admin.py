"""
Админ-панель бота.
Модерация, управление источниками, статистика, рассылка.
"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import config, CATEGORIES, is_admin
from database import db
from keyboards.main import (
    admin_keyboard, 
    moderation_keyboard,
    sources_keyboard,
    vacancy_pagination_keyboard
)

logger = logging.getLogger(__name__)

router = Router()


# =========================================
# FSM СОСТОЯНИЯ ДЛЯ АДМИНА
# =========================================

class AdminStates(StatesGroup):
    """Состояния админ-панели"""
    waiting_for_source = State()
    waiting_for_broadcast = State()
    waiting_for_reject_reason = State()
    waiting_for_default_photo = State()
    waiting_for_faq_photo = State()
    waiting_for_stats_photo = State()
    waiting_for_categories_photo = State()
    waiting_for_welcome_photo = State()
    waiting_for_referral_photo = State()


# =========================================
# ФИЛЬТР АДМИНА
# =========================================

def admin_filter(message_or_callback) -> bool:
    """Проверка является ли пользователь админом"""
    if isinstance(message_or_callback, Message):
        return is_admin(message_or_callback.from_user.id)
    elif isinstance(message_or_callback, CallbackQuery):
        return is_admin(message_or_callback.from_user.id)
    return False


# =========================================
# КОМАНДА /admin
# =========================================

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Открыть админ-панель"""
    if not is_admin(message.from_user.id):
        await message.answer("❌ У вас нет доступа к админ-панели")
        return
    
    stats = await db.get_stats()
    
    text = (
        "Админ‑панель\n\n"
        f"Пользователи: {stats.get('users', 0)}\n"
        f"Вакансии в базе: {stats.get('vacancies', 0)}\n"
        f"На модерации: {stats.get('pending_moderation', 0)}\n"
        f"Источники: {stats.get('active_sources', 0)}"
    )
    
    await message.answer(text, reply_markup=admin_keyboard())


# =========================================
# МОДЕРАЦИЯ ВАКАНСИЙ
# =========================================

@router.callback_query(F.data == "admin:moderation")
async def admin_moderation(callback: CallbackQuery):
    """Показать вакансии на модерацию"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    vacancies = await db.get_pending_user_vacancies(limit=1)
    
    if not vacancies:
        await return_to_admin_menu(callback)
        return
    
    # Показываем первую вакансию
    vacancy = vacancies[0]
    category_name = CATEGORIES.get(vacancy["category"], {}).get("name", vacancy["category"])
    
    # Получаем общее количество
    all_vacancies = await db.get_pending_user_vacancies(limit=100)
    total = len(all_vacancies)
    
    author = vacancy.get('username') or str(vacancy['tg_id'])
    vacancy_text = vacancy['text'][:2000]
    if len(vacancy['text']) > 2000:
        vacancy_text += '...'
    
    text = (
        f"На модерации ({1}/{total})\n\n"
        f"Направление: {category_name}\n"
        f"Автор: @{author}\n"
        f"Контакт: {vacancy['contact']}\n\n"
        f"{vacancy_text}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=vacancy_pagination_keyboard(1, total, vacancy["id"])
    )
    await callback.answer()


# =========================================
# ОДОБРЕНИЕ ВАКАНСИИ
# =========================================

@router.callback_query(F.data.startswith("moderate:approve:"))
async def approve_vacancy(callback: CallbackQuery, bot: Bot):
    """Одобрить вакансию"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    vacancy_id = int(callback.data.split(":")[2])
    
    # Одобряем
    success = await db.approve_user_vacancy(vacancy_id, callback.from_user.id)
    
    if success:
        # Получаем вакансию для рассылки
        vacancy = await db.get_user_vacancy(vacancy_id)
        
        if vacancy:
            # Создаем вакансию в основной таблице для рассылки
            await db.create_vacancy(
                text=vacancy["text"],
                category=vacancy["category"],
                source=f"user:{vacancy['tg_id']}",
                source_message_id=None
            )
            
            # Уведомляем автора
            try:
                await bot.send_message(
                    vacancy["tg_id"],
                    "✅ Твоя вакансия одобрена и будет разослана подписчикам!"
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить автора: {e}")
        
        await callback.answer("✅ Вакансия одобрена!")
        
        # Показываем следующую вакансию или возвращаемся в меню
        vacancies = await db.get_pending_user_vacancies(limit=1)
        if vacancies:
            await admin_moderation(callback)
        else:
            await return_to_admin_menu(callback)
    else:
        await callback.answer("❌ Ошибка одобрения", show_alert=True)


# =========================================
# ОТКЛОНЕНИЕ ВАКАНСИИ
# =========================================

@router.callback_query(F.data.startswith("moderate:reject:"))
async def reject_vacancy(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Отклонить вакансию"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    vacancy_id = int(callback.data.split(":")[2])
    
    # Отклоняем (без причины для простоты, можно добавить FSM для ввода причины)
    success = await db.reject_user_vacancy(vacancy_id, callback.from_user.id, "")
    
    if success:
        # Уведомляем автора
        vacancy = await db.get_user_vacancy(vacancy_id)
        if vacancy:
            try:
                await bot.send_message(
                    vacancy["tg_id"],
                    "❌ К сожалению, твоя вакансия отклонена модератором.\n"
                    "Попробуй переформулировать и отправить снова."
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить автора: {e}")
        
        await callback.answer("❌ Вакансия отклонена")
        
        # Показываем следующую или возвращаемся в меню
        vacancies = await db.get_pending_user_vacancies(limit=1)
        if vacancies:
            await admin_moderation(callback)
        else:
            await return_to_admin_menu(callback)
    else:
        await callback.answer("❌ Ошибка отклонения", show_alert=True)


# =========================================
# ПАГИНАЦИЯ МОДЕРАЦИИ
# =========================================

@router.callback_query(F.data.startswith("moderate:page:"))
async def moderation_page(callback: CallbackQuery):
    """Переключение страницы модерации"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    page = int(callback.data.split(":")[2])
    
    vacancies = await db.get_pending_user_vacancies(limit=100)
    total = len(vacancies)
    
    if page < 1 or page > total:
        await callback.answer("❌ Неверная страница")
        return
    
    vacancy = vacancies[page - 1]
    category_name = CATEGORIES.get(vacancy["category"], {}).get("name", vacancy["category"])
    
    author = vacancy.get('username') or str(vacancy['tg_id'])
    vacancy_text = vacancy['text'][:2000]
    if len(vacancy['text']) > 2000:
        vacancy_text += '...'
    
    text = (
        f"На модерации ({page}/{total})\n\n"
        f"Направление: {category_name}\n"
        f"Автор: @{author}\n"
        f"Контакт: {vacancy['contact']}\n\n"
        f"{vacancy_text}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=vacancy_pagination_keyboard(page, total, vacancy["id"])
    )
    await callback.answer()


# =========================================
# УПРАВЛЕНИЕ ИСТОЧНИКАМИ
# =========================================

@router.callback_query(F.data == "admin:sources")
async def admin_sources(callback: CallbackQuery):
    """Показать источники парсинга"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    sources = await db.get_active_sources()
    
    text = "Источники\n\n"
    
    if sources:
        for s in sources[:10]:
            title = s.get("title") or s["source_id"]
            last_parsed = s.get("last_parsed_at", "никогда")
            if last_parsed and last_parsed != "никогда":
                last_parsed = last_parsed[:16]
            text += f"• {title}\n  Последний парсинг: {last_parsed}\n\n"
    else:
        text += "Источники не добавлены\n"
    
    text += "\nНажмите на источник, чтобы отключить."
    
    await callback.message.edit_text(
        text,
        reply_markup=sources_keyboard(sources)
    )
    await callback.answer()


@router.callback_query(F.data == "source:add")
async def add_source_start(callback: CallbackQuery, state: FSMContext):
    """Начать добавление источника"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_source)
    
    await callback.message.edit_text(
        "Добавление источников\n\n"
        "Отправьте ссылку или @username.\n"
        "Можно добавить несколько источников сразу — каждый на новой строке.\n\n"
        "Пример:\n"
        "@channel1\n"
        "@channel2\n"
        "-1001234567890\n\n"
        "Поддерживаются каналы и группы, доступные вашему аккаунту Telethon.\n\n"
        "Для отмены — /cancel"
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_source)
async def add_source_finish(message: Message, state: FSMContext):
    """Завершить добавление источников (поддерживает список)"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text == "/cancel":
        await state.clear()
        await return_to_admin_menu(message, state)
        return
    
    # Разбиваем текст на строки и обрабатываем каждый источник
    lines = [line.strip() for line in message.text.strip().split('\n') if line.strip()]
    
    if not lines:
        await message.answer(
            "❌ Не найдено источников для добавления.\n"
            "Отправьте @username или ID группы (каждый на новой строке).",
            reply_markup=admin_keyboard()
        )
        await state.clear()
        return
    
    # Статистика
    added_count = 0
    already_exists_count = 0
    error_count = 0
    results = []
    
    # Обрабатываем каждый источник
    for line in lines:
        source_id = line.strip()
        if not source_id:
            continue
        
        # Определяем тип и нормализуем source_id
        original_id = source_id
        
        # Обработка ссылок Telegram
        if source_id.startswith("https://t.me/") or source_id.startswith("t.me/"):
            # Извлекаем username из ссылки
            clean_url = source_id.replace("https://", "").replace("http://", "")
            parts = clean_url.replace("t.me/", "").split("/")
            username = parts[0].strip()
            if username:
                source_id = f"@{username}" if not username.startswith("@") else username
                source_type = "channel"
            else:
                error_count += 1
                results.append(f"❌ {original_id} — неверный формат ссылки")
                continue
        elif source_id.startswith("@"):
            source_type = "channel"
        elif source_id.lstrip("-").isdigit():
            source_type = "group"
        else:
            # Пытаемся определить как канал
            source_type = "channel"
            source_id = f"@{source_id}" if not source_id.startswith("@") else source_id
        
        # Сохраняем в БД
        result = await db.add_source(
            source_type=source_type,
            source_id=source_id,
            title=original_id
        )
        
        if result:
            # Проверяем, был ли источник уже активен до добавления
            # Если метод вернул результат, значит источник теперь активен
            # Проверяем по логам или просто считаем успешным
            added_count += 1
            results.append(f"✅ {original_id}")
        else:
            error_count += 1
            results.append(f"❌ {original_id} — ошибка")
    
    # Формируем итоговое сообщение
    total = len(lines)
    summary = (
        f"📊 Обработано источников: {total}\n"
        f"✅ Успешно добавлено/активировано: {added_count}\n"
        f"❌ Ошибок: {error_count}\n\n"
    )
    
    # Показываем детали (первые 10, если много)
    if len(results) <= 10:
        details = "\n".join(results)
    else:
        details = "\n".join(results[:10]) + f"\n\n... и ещё {len(results) - 10} источников"
    
    final_message = summary + details
    
    # Если сообщение слишком длинное, разбиваем
    if len(final_message) > 4000:
        await message.answer(summary, reply_markup=admin_keyboard())
        # Отправляем детали частями
        chunk_size = 3000
        for i in range(0, len(details), chunk_size):
            chunk = details[i:i + chunk_size]
            await message.answer(chunk)
    else:
        await message.answer(final_message, reply_markup=admin_keyboard())
    
    await state.clear()


@router.callback_query(F.data.startswith("source:remove:"))
async def remove_source(callback: CallbackQuery):
    """Удалить источник"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    source_id = callback.data.replace("source:remove:", "")
    
    success = await db.remove_source(source_id)
    
    if success:
        await callback.answer("Отключено")
        # Возвращаемся в меню после удаления источника
        await return_to_admin_menu(callback)
    else:
        await callback.answer("Не удалось отключить", show_alert=True)
        # Обновляем список если не удалось удалить
        await admin_sources(callback)


# =========================================
# СТАТИСТИКА
# =========================================

@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    """Подробная статистика"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    stats = await db.get_stats()
    
    text = (
        "Статистика\n\n"
        f"Пользователи: {stats.get('users', 0)}\n"
        f"Вакансии в базе: {stats.get('vacancies', 0)}\n"
        f"На модерации: {stats.get('pending_moderation', 0)}\n"
        f"Источники: {stats.get('active_sources', 0)}"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_keyboard()
    )
    await callback.answer()


# =========================================
# РУЧНОЙ ПАРСИНГ
# =========================================

@router.callback_query(F.data == "admin:parse_now")
async def admin_parse_now(callback: CallbackQuery):
    """Запустить парсинг вручную"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await callback.answer("⏳ Запускаю парсинг...")
    
    await callback.message.edit_text(
        "⏳ Парсинг запущен...\n"
        "Это может занять несколько минут."
    )
    
    try:
        from parser.telethon_parser import parser
        
        if not parser.is_authorized:
            await parser.start()
        
        if parser.is_authorized:
            sources_count, vacancies_count = await parser.parse_all_sources()
            
            await callback.message.edit_text(
                "Парсинг завершён.\n\n"
                f"Источники: {sources_count}\n"
                f"Новые вакансии: {vacancies_count}",
                reply_markup=admin_keyboard()
            )
        else:
            await callback.message.edit_text(
                "Telethon не авторизован.\n"
                "Запустите бота локально, чтобы завершить авторизацию.",
                reply_markup=admin_keyboard()
            )
    except Exception as e:
        logger.error(f"Ошибка ручного парсинга: {e}")
        await callback.message.edit_text(
            f"Ошибка парсинга:\n{str(e)[:200]}",
            reply_markup=admin_keyboard()
        )


# =========================================
# РАССЫЛКА
# =========================================

@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Начать рассылку"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_broadcast)
    
    users_count = await db.get_users_count()
    
    await callback.message.edit_text(
        "Рассылка\n\n"
        f"Получатели: {users_count}\n\n"
        "Отправьте текст сообщения.\n"
        "Для отмены — /cancel"
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    """Отправить рассылку"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text == "/cancel":
        await state.clear()
        await return_to_admin_menu(message, state)
        return
    
    broadcast_text = message.text
    
    await state.clear()
    await message.answer("Отправляю…")
    
    users = await db.get_all_active_users()
    success_count = 0
    fail_count = 0
    
    for user in users:
        try:
            await bot.send_message(
                user["tg_id"],
                broadcast_text
            )
            success_count += 1
            
            # Пауза для избежания rate limit
            import asyncio
            await asyncio.sleep(0.1)
            
        except Exception as e:
            fail_count += 1
            logger.warning(f"Не удалось отправить {user['tg_id']}: {e}")
    
    await message.answer(
        "Рассылка завершена.\n\n"
        f"Успешно: {success_count}\n"
        f"Ошибок: {fail_count}",
        reply_markup=admin_keyboard()
    )


# =========================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ВОЗВРАТА В МЕНЮ
# =========================================

async def return_to_admin_menu(message_or_callback, state: FSMContext = None):
    """Вернуться в главное меню админ-панели"""
    if state:
        await state.clear()
    
    stats = await db.get_stats()
    
    text = (
        "Админ‑панель\n\n"
        f"Пользователи: {stats.get('users', 0)}\n"
        f"Вакансии в базе: {stats.get('vacancies', 0)}\n"
        f"На модерации: {stats.get('pending_moderation', 0)}\n"
        f"Источники: {stats.get('active_sources', 0)}"
    )
    
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.edit_text(
            text,
            reply_markup=admin_keyboard()
        )
        await message_or_callback.answer()
    elif isinstance(message_or_callback, Message):
        await message_or_callback.answer(
            text,
            reply_markup=admin_keyboard()
        )


# =========================================
# НАЗАД В АДМИН-ПАНЕЛЬ
# =========================================

@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    """Вернуться в админ-панель"""
    await return_to_admin_menu(callback, state)


# =========================================
# ДЕФОЛТНОЕ ФОТО
# =========================================

@router.callback_query(F.data == "admin:default_photo")
async def admin_default_photo(callback: CallbackQuery, state: FSMContext):
    """Управление дефолтным фото"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    current_photo = await db.get_default_photo()
    
    if current_photo:
        text = (
            "Дефолтное фото\n\n"
            "Фото установлено.\n\n"
            "Отправьте новое фото, чтобы заменить.\n"
            "Для отмены — /cancel"
        )
    else:
        text = (
            "Дефолтное фото\n\n"
            "Фото ещё не установлено.\n\n"
            "Отправьте фото, которое будет добавляться к вакансиям без изображения.\n\n"
            "Для отмены — /cancel"
        )
    
    await state.set_state(AdminStates.waiting_for_default_photo)
    await callback.message.edit_text(text)
    await callback.answer()


@router.message(AdminStates.waiting_for_default_photo, F.photo)
async def receive_default_photo(message: Message, state: FSMContext):
    """Получение дефолтного фото"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        # Получаем file_id фото
        photo = message.photo[-1]  # Берем самое большое фото
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id
        
        # Сохраняем в БД
        success = await db.set_default_photo(
            file_id=file_id,
            file_unique_id=file_unique_id,
            uploaded_by=message.from_user.id
        )
        
        if success:
            await message.answer(
                "Готово. Дефолтное фото обновлено.",
                reply_markup=admin_keyboard()
            )
        else:
            await message.answer(
                "Не удалось сохранить фото. Попробуйте ещё раз.",
                reply_markup=admin_keyboard()
            )
        
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка установки дефолтного фото: {e}")
        await message.answer("Не удалось обработать фото. Попробуйте ещё раз.")


@router.message(AdminStates.waiting_for_default_photo)
async def invalid_default_photo(message: Message, state: FSMContext):
    """Некорректное сообщение при ожидании фото"""
    if message.text == "/cancel":
        await return_to_admin_menu(message, state)
        return
    
    await message.answer(
        "Отправьте фото.\n\nДля отмены — /cancel"
    )


# =========================================
# FAQ ФОТО
# =========================================

@router.callback_query(F.data == "admin:faq_photo")
async def admin_faq_photo(callback: CallbackQuery, state: FSMContext):
    """Управление фото для FAQ"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    current_photo = await db.get_faq_photo()

    if current_photo:
        text = (
            "FAQ фото\n\n"
            "Фото установлено.\n\n"
            "Отправьте новое фото, чтобы заменить.\n"
            "Для отмены — /cancel"
        )
    else:
        text = (
            "FAQ фото\n\n"
            "Фото ещё не установлено.\n\n"
            "Отправьте изображение, которое будет показываться в разделе «Помощь».\n\n"
            "Для отмены — /cancel"
        )

    await state.set_state(AdminStates.waiting_for_faq_photo)
    await callback.message.edit_text(text)
    await callback.answer()


@router.message(AdminStates.waiting_for_faq_photo, F.photo)
async def receive_faq_photo(message: Message, state: FSMContext):
    """Получение фото для FAQ"""
    if not is_admin(message.from_user.id):
        return

    try:
        photo = message.photo[-1]
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id

        success = await db.set_faq_photo(
            file_id=file_id,
            file_unique_id=file_unique_id,
            uploaded_by=message.from_user.id
        )

        if success:
            await message.answer(
                "Готово. FAQ‑фото обновлено.",
                reply_markup=admin_keyboard()
            )
        else:
            await message.answer(
                "Не удалось сохранить фото. Попробуйте ещё раз.",
                reply_markup=admin_keyboard()
            )

        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка установки FAQ фото: {e}")
        await message.answer("Не удалось обработать фото. Попробуйте ещё раз.")


@router.message(AdminStates.waiting_for_faq_photo)
async def invalid_faq_photo(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await return_to_admin_menu(message, state)
        return
    await message.answer("Отправьте фото.\n\nДля отмены — /cancel")


# =========================================
# СТАТИСТИКА ФОТО
# =========================================

@router.callback_query(F.data == "admin:stats_photo")
async def admin_stats_photo(callback: CallbackQuery, state: FSMContext):
    """Управление фото для статистики"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    current_photo = await db.get_stats_photo()
    
    if current_photo:
        text = (
            "Фото статистики\n\n"
            "Фото установлено.\n\n"
            "Отправьте новое фото, чтобы заменить.\n"
            "Для отмены — /cancel"
        )
    else:
        text = (
            "Фото статистики\n\n"
            "Фото ещё не установлено.\n\n"
            "Отправьте фото, которое будет отображаться в разделе статистики.\n\n"
            "Для отмены — /cancel"
        )
    
    await state.set_state(AdminStates.waiting_for_stats_photo)
    await callback.message.edit_text(text)
    await callback.answer()


@router.message(AdminStates.waiting_for_stats_photo, F.photo)
async def receive_stats_photo(message: Message, state: FSMContext):
    """Получение фото для статистики"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        # Получаем file_id фото
        photo = message.photo[-1]  # Берем самое большое фото
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id
        
        # Сохраняем в БД
        success = await db.set_stats_photo(
            file_id=file_id,
            file_unique_id=file_unique_id,
            uploaded_by=message.from_user.id
        )
        
        if success:
            await message.answer(
                "Готово. Фото статистики обновлено.",
                reply_markup=admin_keyboard()
            )
        else:
            await message.answer(
                "Не удалось сохранить фото. Попробуйте ещё раз.",
                reply_markup=admin_keyboard()
            )
        
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка установки фото статистики: {e}")
        await message.answer("Не удалось обработать фото. Попробуйте ещё раз.")


@router.message(AdminStates.waiting_for_stats_photo)
async def invalid_stats_photo(message: Message, state: FSMContext):
    """Некорректное сообщение при ожидании фото статистики"""
    if message.text == "/cancel":
        await return_to_admin_menu(message, state)
        return
    
    await message.answer(
        "Отправьте фото.\n\nДля отмены — /cancel"
    )


# =========================================
# НАПРАВЛЕНИЯ ФОТО
# =========================================

@router.callback_query(F.data == "admin:categories_photo")
async def admin_categories_photo(callback: CallbackQuery, state: FSMContext):
    """Управление фото для направлений"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    current_photo = await db.get_categories_photo()
    
    if current_photo:
        text = (
            "Фото направлений\n\n"
            "Фото установлено.\n\n"
            "Отправьте новое фото, чтобы заменить.\n"
            "Для отмены — /cancel"
        )
    else:
        text = (
            "Фото направлений\n\n"
            "Фото ещё не установлено.\n\n"
            "Отправьте фото, которое будет отображаться в разделе направлений.\n\n"
            "Для отмены — /cancel"
        )
    
    await state.set_state(AdminStates.waiting_for_categories_photo)
    await callback.message.edit_text(text)
    await callback.answer()


@router.message(AdminStates.waiting_for_categories_photo, F.photo)
async def receive_categories_photo(message: Message, state: FSMContext):
    """Получение фото для направлений"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        # Получаем file_id фото
        photo = message.photo[-1]  # Берем самое большое фото
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id
        
        # Сохраняем в БД
        success = await db.set_categories_photo(
            file_id=file_id,
            file_unique_id=file_unique_id,
            uploaded_by=message.from_user.id
        )
        
        if success:
            await message.answer(
                "Готово. Фото направлений обновлено.",
                reply_markup=admin_keyboard()
            )
        else:
            await message.answer(
                "Не удалось сохранить фото. Попробуйте ещё раз.",
                reply_markup=admin_keyboard()
            )
        
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка установки фото направлений: {e}")
        await message.answer("Не удалось обработать фото. Попробуйте ещё раз.")


@router.message(AdminStates.waiting_for_categories_photo)
async def invalid_categories_photo(message: Message, state: FSMContext):
    """Некорректное сообщение при ожидании фото направлений"""
    if message.text == "/cancel":
        await return_to_admin_menu(message, state)
        return
    
    await message.answer(
        "Отправьте фото.\n\nДля отмены — /cancel"
    )


# =========================================
# ПРИВЕТСТВЕННОЕ ФОТО
# =========================================

@router.callback_query(F.data == "admin:welcome_photo")
async def admin_welcome_photo(callback: CallbackQuery, state: FSMContext):
    """Управление фото для приветственного сообщения"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    current_photo = await db.get_welcome_photo()
    
    if current_photo:
        text = (
            "Фото приветствия\n\n"
            "Фото установлено.\n\n"
            "Отправьте новое фото, чтобы заменить.\n"
            "Для отмены — /cancel"
        )
    else:
        text = (
            "Фото приветствия\n\n"
            "Фото ещё не установлено.\n\n"
            "Отправьте фото, которое будет отображаться в приветственном сообщении.\n\n"
            "Для отмены — /cancel"
        )
    
    await state.set_state(AdminStates.waiting_for_welcome_photo)
    await callback.message.edit_text(text)
    await callback.answer()


@router.message(AdminStates.waiting_for_welcome_photo, F.photo)
async def receive_welcome_photo(message: Message, state: FSMContext):
    """Получение фото для приветственного сообщения"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        # Получаем file_id фото
        photo = message.photo[-1]  # Берем самое большое фото
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id
        
        # Сохраняем в БД
        success = await db.set_welcome_photo(
            file_id=file_id,
            file_unique_id=file_unique_id,
            uploaded_by=message.from_user.id
        )
        
        if success:
            await message.answer(
                "Готово. Фото приветствия обновлено.",
                reply_markup=admin_keyboard()
            )
        else:
            await message.answer(
                "Не удалось сохранить фото. Попробуйте ещё раз.",
                reply_markup=admin_keyboard()
            )
        
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка установки фото приветствия: {e}")
        await message.answer("Не удалось обработать фото. Попробуйте ещё раз.")


@router.message(AdminStates.waiting_for_welcome_photo)
async def invalid_welcome_photo(message: Message, state: FSMContext):
    """Некорректное сообщение при ожидании фото приветствия"""
    if message.text == "/cancel":
        await return_to_admin_menu(message, state)
        return
    
    await message.answer(
        "Отправьте фото.\n\nДля отмены — /cancel"
    )


# =========================================
# REFERRAL PHOTO
# =========================================

@router.callback_query(F.data == "admin:referral_photo")
async def admin_referral_photo(callback: CallbackQuery, state: FSMContext):
    """Управление фото для реферальной системы"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    current_photo = await db.get_referral_photo()
    
    if current_photo:
        text = (
            "Рефералка фото\n\n"
            "Фото установлено.\n\n"
            "Отправьте новое фото, чтобы заменить.\n"
            "Для отмены — /cancel"
        )
    else:
        text = (
            "Рефералка фото\n\n"
            "Фото ещё не установлено.\n\n"
            "Отправьте фото, которое будет отображаться в сообщениях о реферальной системе.\n\n"
            "Для отмены — /cancel"
        )
    
    await state.set_state(AdminStates.waiting_for_referral_photo)
    await callback.message.edit_text(text)
    await callback.answer()


@router.message(AdminStates.waiting_for_referral_photo, F.photo)
async def receive_referral_photo(message: Message, state: FSMContext):
    """Получение фото для реферальной системы"""
    if not is_admin(message.from_user.id):
        return
    
    try:
        # Получаем file_id фото
        photo = message.photo[-1]  # Берем самое большое фото
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id
        
        # Сохраняем в БД
        success = await db.set_referral_photo(
            file_id=file_id,
            file_unique_id=file_unique_id,
            uploaded_by=message.from_user.id
        )
        
        if success:
            await message.answer(
                "Готово. Рефералка фото обновлено.",
                reply_markup=admin_keyboard()
            )
        else:
            await message.answer(
                "Не удалось сохранить фото. Попробуйте ещё раз.",
                reply_markup=admin_keyboard()
            )
        
        await state.clear()
    except Exception as e:
        logger.error(f"Ошибка установки реферального фото: {e}")
        await message.answer("Не удалось обработать фото. Попробуйте ещё раз.")


@router.message(AdminStates.waiting_for_referral_photo)
async def invalid_referral_photo(message: Message, state: FSMContext):
    """Некорректное сообщение при ожидании реферального фото"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отмена. Возврат в админ-панель.", reply_markup=admin_keyboard())
        return
    
    await message.answer(
        "Отправьте фото.\n\nДля отмены — /cancel"
    )


# =========================================
# МОДЕРАЦИЯ ОТЗЫВОВ
# =========================================

@router.callback_query(F.data == "admin:reviews_moderation")
async def admin_reviews_moderation(callback: CallbackQuery):
    """Показать отзывы на модерацию"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    logger.info("Запрос отзывов на модерацию...")
    reviews = await db.get_pending_reviews(limit=1)
    logger.info(f"Получено отзывов: {len(reviews) if reviews else 0}")
    
    if not reviews:
        # Проверяем все отзывы для диагностики
        all_reviews = await db.get_all_reviews(limit=100)
        logger.info(f"Всего отзывов в БД: {len(all_reviews) if all_reviews else 0}")
        
        # Формируем диагностическое сообщение
        if all_reviews:
            status_info = {}
            for review in all_reviews:
                status = review.get("status", "unknown")
                status_info[status] = status_info.get(status, 0) + 1
            status_text = ", ".join([f"{k}: {v}" for k, v in status_info.items()])
            diagnostic_msg = f"\n\n📊 Диагностика: Всего отзывов в БД: {len(all_reviews)}, статусы: {status_text}"
        else:
            diagnostic_msg = "\n\n📊 Диагностика: В БД нет отзывов"
        
        await callback.message.edit_text(
            f"На модерации отзывов пока пусто.{diagnostic_msg}",
            reply_markup=admin_keyboard()
        )
        await callback.answer()
        return
    
    # Показываем первый отзыв
    review = reviews[0]
    review_id = review["id"]
    
    # Получаем общее количество
    all_reviews = await db.get_pending_reviews(limit=100)
    total = len(all_reviews)
    
    username = review.get("username") or "Без username"
    first_name = review.get("first_name") or ""
    rating = review.get("rating")
    text = review.get("text", "")
    
    review_text = (
        f"📝 <b>Отзыв #{review_id}</b>\n\n"
        f"👤 <b>Пользователь:</b> {first_name} (@{username})\n"
        f"🆔 <b>ID:</b> {review['tg_id']}\n"
    )
    
    if rating:
        stars = "⭐" * rating
        review_text += f"⭐ <b>Оценка:</b> {rating}/5 {stars}\n\n"
    else:
        review_text += "\n"
    
    review_text += f"💬 <b>Текст отзыва:</b>\n<blockquote>{text}</blockquote>\n\n"
    review_text += f"📊 Всего на модерации: {total}"
    
    await callback.message.edit_text(
        review_text,
        parse_mode="HTML",
        reply_markup=reviews_moderation_keyboard(review_id, total)
    )
    await callback.answer()


def reviews_moderation_keyboard(review_id: int, total: int) -> InlineKeyboardMarkup:
    """Клавиатура модерации отзыва"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="✅ Одобрить",
            callback_data=f"review:approve:{review_id}"
        ),
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=f"review:reject:{review_id}"
        )
    )
    
    if total > 1:
        builder.row(
            InlineKeyboardButton(
                text="➡️ Следующий",
                callback_data="review:skip"
            )
        )
    
    builder.row(
        InlineKeyboardButton(
            text="В панель",
            callback_data="admin:back"
        )
    )
    
    return builder.as_markup()


@router.callback_query(F.data.startswith("review:approve:"))
async def approve_review(callback: CallbackQuery, bot: Bot):
    """Одобрить отзыв"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    review_id = int(callback.data.split(":")[2])
    
    # Одобряем отзыв и начисляем x2
    success = await db.approve_review(review_id, callback.from_user.id)
    
    if success:
        # Уведомляем пользователя
        review = await db.get_review(review_id)
        if review:
            try:
                await bot.send_message(
                    review["tg_id"],
                    "✅ <b>Ваш отзыв одобрен!</b>\n\n"
                    "🎉 Вам начислено <b>3 дня x2 статуса</b>!\n\n"
                    "✨ Теперь вы будете получать <b>100% вакансий</b> вместо 90%.\n\n"
                    "Спасибо за ваш отзыв! 🙏",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Не удалось уведомить пользователя об одобрении отзыва: {e}")
            
            # Публикуем отзыв в канал
            reviews_channel = config.channel.reviews_channel
            if reviews_channel:
                try:
                    # Форматируем отзыв для публикации
                    author_name = review.get("first_name", "Пользователь")
                    username = review.get("username")
                    rating = review.get("rating")
                    text = review.get("text", "")
                    
                    # Формируем красивое сообщение
                    stars = "⭐" * rating if rating else ""
                    rating_text = f"{stars} ({rating}/5)" if rating else ""
                    
                    # Формируем имя автора
                    if username:
                        author_display = f"@{username}"
                    else:
                        author_display = author_name
                    
                    # Формируем текст публикации
                    publication_text = (
                        "💬 <b>Новый отзыв о FreelanceHub</b>\n\n"
                        f"👤 <b>Автор:</b> {author_display}\n"
                    )
                    
                    if rating_text:
                        publication_text += f"⭐ <b>Оценка:</b> {rating_text}\n\n"
                    
                    publication_text += (
                        "<blockquote>"
                        f"{text}"
                        "</blockquote>"
                    )
                    
                    # Отправляем в канал
                    await bot.send_message(
                        chat_id=reviews_channel,
                        text=publication_text,
                        parse_mode="HTML"
                    )
                    logger.info(f"✅ Отзыв {review_id} опубликован в канал {reviews_channel}")
                except Exception as e:
                    logger.error(f"Ошибка публикации отзыва {review_id} в канал: {e}")
        
        await callback.answer("✅ Отзыв одобрен, x2 начислен")
        
        # Показываем следующий отзыв или возвращаемся в меню
        reviews = await db.get_pending_reviews(limit=1)
        if reviews:
            await admin_reviews_moderation(callback)
        else:
            await return_to_admin_menu(callback)
    else:
        await callback.answer("❌ Ошибка одобрения", show_alert=True)


@router.callback_query(F.data.startswith("review:reject:"))
async def reject_review(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Отклонить отзыв"""
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    review_id = int(callback.data.split(":")[2])
    
    # Сохраняем ID отзыва для ввода причины
    await state.update_data(review_id=review_id)
    await state.set_state(AdminStates.waiting_for_reject_reason)
    
    await callback.message.edit_text(
        "❌ <b>Отклонить отзыв</b>\n\n"
        "Введите причину отклонения (или отправьте /skip чтобы пропустить):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_reject_reason)
async def receive_reject_reason(message: Message, state: FSMContext, bot: Bot):
    """Получение причины отклонения отзыва"""
    if not is_admin(message.from_user.id):
        return
    
    if message.text == "/cancel":
        await return_to_admin_menu(message, state)
        return
    
    data = await state.get_data()
    review_id = data.get("review_id")
    
    if not review_id:
        await state.clear()
        await message.answer("Ошибка: ID отзыва не найден.")
        return
    
    reason = message.text if message.text != "/skip" else ""
    
    # Отклоняем отзыв
    success = await db.reject_review(review_id, message.from_user.id, reason)
    
    if success:
        # Уведомляем пользователя
        review = await db.get_review(review_id)
        if review:
            try:
                rejection_msg = "❌ К сожалению, ваш отзыв отклонен модератором."
                if reason:
                    rejection_msg += f"\n\nПричина: {reason}"
                await bot.send_message(review["tg_id"], rejection_msg)
            except Exception as e:
                logger.warning(f"Не удалось уведомить пользователя об отклонении отзыва: {e}")
        
        await message.answer("✅ Отзыв отклонен", reply_markup=admin_keyboard())
    
    await state.clear()
    
    # Показываем следующий отзыв или возвращаемся в меню
    reviews = await db.get_pending_reviews(limit=1)
    if reviews:
        # Создаем временный callback для вызова функции модерации
        class FakeCallback:
            def __init__(self, msg):
                self.message = msg
                self.from_user = msg.from_user
            
            async def answer(self, text=None, show_alert=False):
                pass
        
        fake_callback = FakeCallback(message)
        await admin_reviews_moderation(fake_callback)
    else:
        # Возвращаемся в меню
        await return_to_admin_menu(message, state)


@router.callback_query(F.data == "review:skip")
async def skip_review(callback: CallbackQuery):
    """Пропустить отзыв (показать следующий)"""
    await admin_reviews_moderation(callback)
