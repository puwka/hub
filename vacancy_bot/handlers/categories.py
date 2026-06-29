"""
Обработчики выбора категорий.
"""

import logging
import re
import html
from typing import Dict, List
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import CATEGORIES, config, REFERRAL_BONUS_DAYS, REVIEW_BONUS_DAYS
from database import db
from keyboards import categories_keyboard, main_menu_keyboard

logger = logging.getLogger(__name__)


def truncate_html_safe(text: str, max_length: int) -> str:
    """
    Безопасная обрезка HTML-текста с закрытием всех открытых тегов.
    """
    if len(text) <= max_length:
        return text
    
    target_length = max_length - 100
    safe_pos = target_length
    tag_pattern = re.compile(r'<[^>]+>')
    
    for match in tag_pattern.finditer(text[:target_length + 50]):
        if match.end() <= target_length:
            safe_pos = match.end()
        elif match.start() < target_length < match.end():
            safe_pos = match.start()
            break
    
    truncated = text[:safe_pos]
    
    open_tags = []
    tag_open_pattern = re.compile(r'<(\w+)[^>]*/?>')
    tag_close_pattern = re.compile(r'</(\w+)>')
    
    for match in tag_open_pattern.finditer(truncated):
        tag_name = match.group(1).lower()
        tag_full = match.group(0)
        if tag_name not in ['br', 'hr', 'img', 'input'] and not tag_full.endswith('/>'):
            open_tags.append(tag_name)
    
    for match in tag_close_pattern.finditer(truncated):
        tag_name = match.group(1).lower()
        if tag_name in open_tags:
            open_tags.remove(tag_name)
    
    closed_tags = ''.join([f'</{tag}>' for tag in reversed(open_tags)])
    result = truncated + '...' + closed_tags
    
    if len(result) > max_length:
        new_target = max_length - len(closed_tags) - 3
        truncated = text[:new_target]
        result = truncated + '...' + closed_tags
    
    return result

router = Router()


# Временное хранилище выбранных категорий (в памяти)
# В production лучше использовать FSM или Redis
user_category_selections: Dict[int, List[str]] = {}


# =========================================
# КОМАНДА /categories
# =========================================

@router.message(Command("categories"))
@router.message(F.text == "Мои направления")
async def cmd_categories(message: Message):
    """Показать меню выбора категорий"""
    user = await db.get_user(message.from_user.id)
    
    current_categories = user.get("categories", []) if user else []
    
    # Сохраняем текущий выбор во временное хранилище
    user_category_selections[message.from_user.id] = list(current_categories)
    
    # Формируем список выбранных направлений
    if current_categories:
        categories_list = []
        for c in current_categories:
            cat_data = CATEGORIES.get(c, {})
            categories_list.append(cat_data.get("name", c))
        categories_text = "\n".join(categories_list)
    else:
        categories_text = "Не выбраны"
    
    # Формируем текст с инструкцией в цитате
    header = "🎯 <b>Мои направления</b>\n\n"
    
    instruction = (
        "<i>Выберите направления, которые вам интересны.\n"
        "Можно выбрать несколько. После выбора нажмите «Сохранить».</i>"
    )
    
    content = (
        f"{instruction}\n\n"
        f"<b>Ваши направления:</b>\n"
        f"{categories_text}"
    )
    
    # Оборачиваем содержимое в цитату
    text = f"{header}<blockquote>{content}</blockquote>"
    
    # Проверяем есть ли фото направлений
    categories_photo_id = await db.get_categories_photo()
    
    if categories_photo_id:
        # Отправляем фото с текстом в caption
        max_caption_length = 1024
        if len(text) > max_caption_length:
            text = truncate_html_safe(text, max_caption_length)
        
        try:
            await message.answer_photo(
                photo=categories_photo_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=categories_keyboard(current_categories)
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить фото направлений: {e}")
            # Fallback: отправляем только текст
            try:
                await message.answer(
                    text,
                    parse_mode="HTML",
                    reply_markup=categories_keyboard(current_categories)
                )
            except:
                import html
                import re
                plain_text = html.unescape(re.sub(r'<[^>]+>', '', text))
                await message.answer(
                    plain_text,
                    reply_markup=categories_keyboard(current_categories)
                )
    else:
        # Если фото нет - отправляем только текст
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=categories_keyboard(current_categories)
        )


# =========================================
# ВЫБОР КАТЕГОРИИ (toggle)
# =========================================

@router.callback_query(F.data.startswith("category:"))
async def category_callback(callback: CallbackQuery):
    """Обработка выбора категории"""
    action = callback.data.split(":")[1]
    user_id = callback.from_user.id
    
    # Получаем текущий выбор
    if user_id not in user_category_selections:
        user = await db.get_user(user_id)
        user_category_selections[user_id] = list(user.get("categories", []) if user else [])
    
    selected = user_category_selections[user_id]
    
    # =========================================
    # СБРОС ВЫБОРА
    # =========================================
    if action == "reset":
        user_category_selections[user_id] = []
        
        await callback.message.edit_text(
            "Выбор сброшен. Выберите направления заново:",
            reply_markup=categories_keyboard([])
        )
        await callback.answer("Готово")
        return
    
    # =========================================
    # СОХРАНЕНИЕ
    # =========================================
    if action == "save":
        if not selected:
            await callback.answer(
                "Выберите хотя бы одно направление, чтобы продолжить.",
                show_alert=True
            )
            return
        
        # Сохраняем в БД
        success = await db.update_user_categories(user_id, selected)
        
        if success:
            # Формируем список направлений (каждая на новой строке)
            categories_list = "\n".join([
                CATEGORIES.get(c, {}).get("name", c) 
                for c in selected
            ])
            
            # Формируем текст: "Настройки обновлены" жирным, направления в цитате
            success_text = (
                "<b>Настройки обновлены.</b>\n\n"
                "<blockquote>"
                f"Направления:\n{categories_list}\n\n"
                "Вакансии будут приходить по выбранным направлениям."
                "</blockquote>"
            )
            
            # Проверяем, есть ли фото в сообщении
            # Если есть фото - редактируем caption, если нет - редактируем text
            try:
                if callback.message.photo:
                    # Сообщение с фото - редактируем caption
                    await callback.message.edit_caption(
                        caption=success_text,
                        reply_markup=None,
                        parse_mode="HTML"
                    )
                else:
                    # Текстовое сообщение - редактируем text
                    await callback.message.edit_text(
                        success_text,
                        reply_markup=None,
                        parse_mode="HTML"
                    )
            except Exception as e:
                # Если не удалось отредактировать - отправляем новое сообщение
                logger.warning(f"Не удалось отредактировать сообщение: {e}")
                await callback.message.answer(success_text)
            
            # Очищаем временное хранилище
            del user_category_selections[user_id]
            
            await callback.answer("Сохранено")
            
            # Отправляем главное меню
            # Используем минимальный текст, так как Telegram требует непустой текст
            await callback.message.answer(
                ".",
                reply_markup=main_menu_keyboard()
            )
            
            # Отправляем рекламу реферальной системы и информации об отзывах
            referral_code = None
            feedback_link = None
            
            # Получаем или создаем реферальный код
            try:
                stats = await db.get_referral_stats(user_id)
                referral_code = stats.get("referral_code")
                
                # Если реферального кода нет - создаем его
                if not referral_code:
                    referral_code = await db.create_referral_code(user_id)
            except Exception as ref_code_error:
                logger.warning(f"Ошибка получения/создания реферального кода для {user_id}: {ref_code_error}")
            
            # Получаем ссылку на бота отзывов
            try:
                feedback_bot = config.channel.feedback_bot
                if feedback_bot:
                    # Убираем @ если есть
                    feedback_bot_clean = feedback_bot.replace('@', '').strip()
                    if feedback_bot_clean:
                        feedback_link = f"https://t.me/{feedback_bot_clean}"
            except Exception as feedback_error:
                logger.warning(f"Ошибка получения ссылки на бота отзывов: {feedback_error}")
            
            # Формируем текст сообщения (базовый текст всегда есть)
            referral_text = (
                "🎁 <b>Пригласи друзей и получай больше вакансий!</b>\n\n"
            )
            
            # Добавляем реферальную ссылку если есть код
            if referral_code:
                try:
                    bot_username = (await callback.bot.get_me()).username
                    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
                    referral_text += (
                        f"📋 <b>Твоя реферальная ссылка:</b>\n"
                        f"<code>{referral_link}</code>\n\n"
                    )
                except Exception as bot_error:
                    logger.warning(f"Ошибка получения username бота: {bot_error}")
            
            # Добавляем информацию о реферальной системе
            referral_text += (
                f"<blockquote>💡 За каждого приглашённого друга ты получаешь "
                f"+{REFERRAL_BONUS_DAYS} день к подписке.\n"
                "Без активной подписки вакансии не приходят.</blockquote>"
            )
            
            # Добавляем информацию о системе отзывов
            if feedback_link:
                referral_text += (
                    "\n\n"
                    f"💬 <b>Оставь отзыв и получи {REVIEW_BONUS_DAYS} дня подписки!</b>\n\n"
                    f"📝 Перейди в бот отзывов: {feedback_link}\n\n"
                    f"<blockquote>✨ За каждый одобренный отзыв ты получишь "
                    f"<b>{REVIEW_BONUS_DAYS} дня подписки</b>!\n"
                    "Отзыв проходит модерацию перед одобрением.</blockquote>"
                )
            
            # Создаем клавиатуру
            from aiogram.types import InlineKeyboardButton
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            
            keyboard = InlineKeyboardBuilder()
            
            # Добавляем кнопку "Поделиться ссылкой" только если есть реферальный код
            if referral_code:
                try:
                    bot_username = (await callback.bot.get_me()).username
                    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
                    keyboard.row(
                        InlineKeyboardButton(
                            text="Поделиться ссылкой",
                            url=f"https://t.me/share/url?url={referral_link}&text=Присоединяйся к FreelanceHub!"
                        )
                    )
                except Exception as bot_error:
                    logger.warning(f"Ошибка создания кнопки реферальной ссылки: {bot_error}")
            
            # Добавляем кнопку "Оставить отзыв" если есть бот отзывов
            if feedback_link:
                keyboard.row(
                    InlineKeyboardButton(
                        text="Оставить отзыв",
                        url=feedback_link
                    )
                )
            
            # Отправляем сообщение (всегда, даже если нет кнопок)
            try:
                # Получаем фото для реферальной системы
                referral_photo = await db.get_referral_photo()
                
                # Отправляем сообщение с фото или без
                if referral_photo:
                    referral_message = await callback.message.answer_photo(
                        photo=referral_photo,
                        caption=referral_text,
                        parse_mode="HTML",
                        reply_markup=keyboard.as_markup() if keyboard.buttons else None
                    )
                else:
                    referral_message = await callback.message.answer(
                        referral_text,
                        parse_mode="HTML",
                        reply_markup=keyboard.as_markup() if keyboard.buttons else None
                    )
                
                # Пытаемся закрепить сообщение
                try:
                    await callback.bot.pin_chat_message(
                        chat_id=callback.message.chat.id,
                        message_id=referral_message.message_id,
                        disable_notification=True
                    )
                    logger.info(f"✅ Закреплено реферальное сообщение для пользователя {user_id}")
                except Exception as pin_error:
                    error_msg = str(pin_error).lower()
                    # Если уже есть закрепленное сообщение - это нормально, просто логируем
                    if "already pinned" in error_msg or "chat not found" in error_msg or "message not found" in error_msg:
                        logger.debug(f"ℹ️ Не удалось закрепить сообщение для пользователя {user_id}: уже есть закрепленное или чат не найден")
                    else:
                        # Другие ошибки логируем как предупреждение
                        logger.warning(f"⚠️ Ошибка закрепления сообщения для пользователя {user_id}: {pin_error}")
            except Exception as send_error:
                logger.error(f"Ошибка отправки реферального сообщения для пользователя {user_id}: {send_error}")
                logger.exception(send_error)  # Полный traceback для отладки
        else:
            await callback.answer("Не удалось сохранить. Попробуйте ещё раз.", show_alert=True)
        return
    
    # =========================================
    # TOGGLE КАТЕГОРИИ
    # =========================================
    category_id = action
    
    if category_id not in CATEGORIES:
        await callback.answer("❌ Неизвестная категория")
        return
    
    # Переключаем выбор
    if category_id in selected:
        selected.remove(category_id)
        await callback.answer("Убрано")
    else:
        selected.append(category_id)
        await callback.answer("Добавлено")
    
    user_category_selections[user_id] = selected
    
    # Обновляем клавиатуру (работает и для фото, и для текста)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=categories_keyboard(selected)
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить клавиатуру: {e}")
        # Если не удалось обновить клавиатуру - просто игнорируем ошибку
        # Клавиатура уже обновлена в памяти, при следующем взаимодействии будет актуальной


# =========================================
# БЫСТРЫЙ ВЫБОР ВСЕХ КАТЕГОРИЙ
# =========================================

@router.message(Command("all_categories"))
async def cmd_all_categories(message: Message):
    """Выбрать все категории"""
    all_cats = list(CATEGORIES.keys())
    
    success = await db.update_user_categories(message.from_user.id, all_cats)
    
    if success:
        await message.answer(
            "Готово. Вы включили все направления.",
            reply_markup=main_menu_keyboard()
        )
    else:
        await message.answer("Не удалось сохранить. Попробуйте ещё раз.")



