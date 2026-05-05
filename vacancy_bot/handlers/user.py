"""
Основные обработчики для пользователей.
Старт, подписка, помощь.
"""

import logging
import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.enums import ChatMemberStatus

from config import config, CATEGORIES
from database import db
from keyboards import main_menu_keyboard, subscription_keyboard

logger = logging.getLogger(__name__)


def truncate_html_safe(text: str, max_length: int) -> str:
    """
    Безопасная обрезка HTML-текста с закрытием всех открытых тегов.
    
    Args:
        text: HTML-текст для обрезки
        max_length: Максимальная длина
        
    Returns:
        Обрезанный текст с закрытыми тегами
    """
    if len(text) <= max_length:
        return text
    
    # Оставляем запас для закрывающих тегов и многоточия
    target_length = max_length - 100
    
    # Находим последнюю безопасную позицию обрезки (не внутри тега)
    safe_pos = target_length
    tag_pattern = re.compile(r'<[^>]+>')
    
    # Ищем все теги до позиции обрезки
    for match in tag_pattern.finditer(text[:target_length + 50]):
        if match.end() <= target_length:
            safe_pos = match.end()
        elif match.start() < target_length < match.end():
            # Обрезка попадает внутрь тега - обрезаем до начала тега
            safe_pos = match.start()
            break
    
    truncated = text[:safe_pos]
    
    # Находим все незакрытые теги
    open_tags = []
    tag_open_pattern = re.compile(r'<(\w+)[^>]*/?>')
    tag_close_pattern = re.compile(r'</(\w+)>')
    
    for match in tag_open_pattern.finditer(truncated):
        tag_name = match.group(1).lower()
        tag_full = match.group(0)
        # Игнорируем самозакрывающиеся теги
        if tag_name not in ['br', 'hr', 'img', 'input'] and not tag_full.endswith('/>'):
            open_tags.append(tag_name)
    
    for match in tag_close_pattern.finditer(truncated):
        tag_name = match.group(1).lower()
        if tag_name in open_tags:
            open_tags.remove(tag_name)
    
    # Закрываем все открытые теги в обратном порядке
    closed_tags = ''.join([f'</{tag}>' for tag in reversed(open_tags)])
    
    result = truncated + '...' + closed_tags
    
    # Если результат все еще слишком длинный, обрезаем еще раз
    if len(result) > max_length:
        # Убираем закрывающие теги и обрезаем еще больше
        new_target = max_length - len(closed_tags) - 3
        truncated = text[:new_target]
        result = truncated + '...' + closed_tags
    
    return result

router = Router()


# =========================================
# ПРОВЕРКА ПОДПИСКИ
# =========================================

async def check_channel_subscription(bot: Bot, user_id: int) -> bool:
    """Проверить подписан ли пользователь на обязательный канал"""
    if not config.channel.required_channel:
        return True  # Если канал не указан - пропускаем проверку
    
    try:
        member = await bot.get_chat_member(
            chat_id=config.channel.required_channel,
            user_id=user_id
        )
        
        # Статусы которые считаем подпиской
        valid_statuses = [
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR
        ]
        
        return member.status in valid_statuses
        
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для {user_id}: {e}")
        return False


# =========================================
# КОМАНДА /start
# =========================================

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    """Обработчик команды /start"""
    user = message.from_user
    
    # Проверяем реферальный код в команде /start
    referred_by = None
    if message.text and len(message.text.split()) > 1:
        referral_code = message.text.split()[1]
        referrer = await db.get_user_by_referral_code(referral_code)
        if referrer and referrer["tg_id"] != user.id:
            referred_by = referrer["tg_id"]
    
    # Создаем или получаем пользователя из БД
    db_user = await db.get_or_create_user(
        tg_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        referred_by=referred_by
    )
    
    # Проверяем подписку на канал
    is_subscribed = await check_channel_subscription(bot, user.id)
    
    if is_subscribed:
        # Обновляем статус в БД
        await db.update_user_subscription(user.id, True)
        
        # Формируем информативное приветственное сообщение
        header = "👋 <b>Добро пожаловать в FreelanceHub</b>\n\n"
        
        info_text = (
            "🎯 FreelanceHub — это Telegram-бот, который собирает актуальные вакансии "
            "и заказы для фрилансеров из проверенных источников.\n\n"
            "<blockquote>✨ Выберите интересующие направления — и получайте только релевантные вакансии "
            "без спама и дублей. Все вакансии проходят модерацию перед рассылкой.</blockquote>\n\n"
            "🚀 Начните с выбора направлений, чтобы получать подходящие предложения."
        )
        
        welcome_text = f"{header}{info_text}"
        
        # Формируем клавиатуру с кнопкой "Выбрать профессии"
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        
        welcome_keyboard = InlineKeyboardBuilder()
        welcome_keyboard.row(
            InlineKeyboardButton(
                text="Выбрать профессии",
                callback_data="select_categories"
            )
        )
        
        # Проверяем есть ли фото приветствия
        welcome_photo_id = await db.get_welcome_photo()
        
        if welcome_photo_id:
            # Отправляем фото с текстом в caption
            max_caption_length = 1024
            if len(welcome_text) > max_caption_length:
                welcome_text = truncate_html_safe(welcome_text, max_caption_length)
            
            try:
                sent_message = await message.answer_photo(
                    photo=welcome_photo_id,
                    caption=welcome_text,
                    parse_mode="HTML",
                    reply_markup=welcome_keyboard.as_markup()
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить фото приветствия: {e}")
                # Fallback: отправляем только текст
                try:
                    sent_message = await message.answer(
                        welcome_text,
                        parse_mode="HTML",
                        reply_markup=welcome_keyboard.as_markup()
                    )
                except:
                    import html
                    plain_text = html.unescape(re.sub(r'<[^>]+>', '', welcome_text))
                    sent_message = await message.answer(
                        plain_text,
                        reply_markup=welcome_keyboard.as_markup()
                    )
        else:
            # Если фото нет - отправляем только текст
            sent_message = await message.answer(
                welcome_text,
                parse_mode="HTML",
                reply_markup=welcome_keyboard.as_markup()
            )
        
        # Отправляем главное меню с кнопками (reply keyboard)
        # Используем невидимый символ zero-width space, который не отображается
        await message.answer(
            "\u200B",
            reply_markup=main_menu_keyboard()
        )
        
        # Если категории еще не выбраны - предлагаем выбрать
        if not db_user or not db_user.get("categories"):
            from keyboards.main import categories_keyboard
            await message.answer(
                "Выберите направления, которые вам интересны. Можно выбрать несколько.",
                reply_markup=categories_keyboard()
            )
    else:
        # Просим подписаться
        await message.answer(
            "Для доступа к вакансиям нужна подписка на наш официальный канал.\n"
            "Это защита от ботов и спама.\n\n"
            "Подпишитесь и нажмите «Проверить».",
            reply_markup=subscription_keyboard(config.channel.required_channel)
        )


# =========================================
# ОБРАБОТЧИК КНОПКИ "ВЫБРАТЬ ПРОФЕССИИ"
# =========================================

@router.callback_query(F.data == "select_categories")
async def select_categories_from_welcome(callback: CallbackQuery):
    """Обработка кнопки 'Выбрать профессии' из приветственного сообщения"""
    user = await db.get_user(callback.from_user.id)
    current_categories = user.get("categories", []) if user else []
    
    from handlers.categories import user_category_selections
    user_category_selections[callback.from_user.id] = list(current_categories)
    
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
    
    from keyboards.main import categories_keyboard
    
    if categories_photo_id:
        # Отправляем фото с текстом в caption
        max_caption_length = 1024
        if len(text) > max_caption_length:
            text = truncate_html_safe(text, max_caption_length)
        
        try:
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=categories_photo_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=categories_keyboard(current_categories)
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить фото направлений: {e}")
            try:
                await callback.message.edit_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=categories_keyboard(current_categories)
                )
            except:
                await callback.message.answer(
                    text,
                    parse_mode="HTML",
                    reply_markup=categories_keyboard(current_categories)
                )
    else:
        # Если фото нет - отправляем только текст
        try:
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=categories_keyboard(current_categories)
            )
        except:
            await callback.message.answer(
                text,
                parse_mode="HTML",
                reply_markup=categories_keyboard(current_categories)
            )
    
    await callback.answer()


# =========================================
# КОМАНДА /ref - РЕФЕРАЛЬНАЯ СИСТЕМА
# =========================================

@router.message(Command("ref"))
async def cmd_ref(message: Message):
    """Показать реферальную ссылку и статистику"""
    user = await db.get_user(message.from_user.id)
    
    if not user:
        await message.answer("❌ Ошибка: пользователь не найден")
        return
    
    stats = await db.get_referral_stats(message.from_user.id)
    referral_code = stats.get("referral_code")
    referral_count = stats.get("referral_count", 0)
    x2_active = stats.get("x2_active", False)
    x2_until = stats.get("x2_until")
    
    # Если реферального кода нет - создаем его
    if not referral_code:
        referral_code = await db.create_referral_code(message.from_user.id)
        if not referral_code:
            await message.answer("❌ Ошибка: не удалось создать реферальный код")
            return
    
    # Формируем реферальную ссылку
    bot_username = (await message.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    # Формируем текст сообщения
    text = (
        "🎁 <b>Реферальная система</b>\n\n"
        f"📋 <b>Ваша ссылка:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"👥 <b>Приглашено друзей:</b> {referral_count}\n\n"
    )
    
    # Проверяем статус x2 напрямую из БД
    x2_active_check = await db.is_user_x2(message.from_user.id)
    
    if x2_active_check and x2_until:
        try:
            from datetime import datetime, timezone
            # Пробуем разные форматы даты
            x2_str = x2_until.replace('Z', '+00:00')
            if '+' not in x2_str and 'T' in x2_str:
                x2_str += '+00:00'
            x2_until_dt = datetime.fromisoformat(x2_str)
            
            # Делаем aware если нужно
            if x2_until_dt.tzinfo is None:
                x2_until_dt = x2_until_dt.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            hours_left = int((x2_until_dt - now).total_seconds() / 3600)
            if hours_left > 0:
                text += f"⚡ <b>Статус x2 активен</b>\n"
                text += f"⏰ Осталось: {hours_left} часов\n\n"
            else:
                text += "⚡ <b>Статус x2:</b> Неактивен\n\n"
        except Exception as e:
            logger.error(f"Ошибка форматирования x2_until: {e}, значение: {x2_until}")
            if x2_active_check:
                text += f"⚡ <b>Статус x2 активен</b>\n\n"
            else:
                text += "⚡ <b>Статус x2:</b> Неактивен\n\n"
    else:
        text += "⚡ <b>Статус x2:</b> Неактивен\n\n"
    
    text += (
        "<blockquote>💡 За каждого приглашенного друга вы получаете +24 часа статуса x2.\n"
        "Пользователи с x2 получают 100% вакансий, обычные — 80%.</blockquote>"
    )
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(
            text="Поделиться ссылкой",
            url=f"https://t.me/share/url?url={referral_link}&text=Присоединяйся к FreelanceHub!"
        )
    )
    
    # Получаем фото для реферальной системы
    referral_photo = await db.get_referral_photo()
    
    # Отправляем сообщение с фото или без
    if referral_photo:
        # Проверяем длину caption (максимум 1024 символа)
        max_caption_length = 1024
        caption = text
        if len(caption) > max_caption_length:
            caption = truncate_html_safe(caption, max_caption_length)
        
        try:
            await message.answer_photo(
                photo=referral_photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard.as_markup()
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить фото реферальной системы: {e}")
            # Fallback: отправляем только текст
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())


# =========================================
# CALLBACK РЕФЕРАЛЬНОЙ СИСТЕМЫ ИЗ ПОМОЩИ
# =========================================

@router.callback_query(F.data == "show_referral")
async def show_referral_callback(callback: CallbackQuery):
    """Показать информацию о реферальной системе из кнопки в помощи"""
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await callback.answer("❌ Ошибка: пользователь не найден", show_alert=True)
        return
    
    stats = await db.get_referral_stats(user_id)
    referral_code = stats.get("referral_code")
    referral_count = stats.get("referral_count", 0)
    x2_active = stats.get("x2_active", False)
    x2_until = stats.get("x2_until")
    
    # Если реферального кода нет - создаем его
    if not referral_code:
        referral_code = await db.create_referral_code(user_id)
        if not referral_code:
            await callback.answer("❌ Ошибка: не удалось создать реферальный код", show_alert=True)
            return
    
    # Формируем реферальную ссылку
    bot_username = (await callback.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    # Формируем текст сообщения
    text = (
        "🎁 <b>Реферальная система</b>\n\n"
        f"📋 <b>Ваша ссылка:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"👥 <b>Приглашено друзей:</b> {referral_count}\n\n"
    )
    
    # Проверяем статус x2 напрямую из БД
    x2_active_check = await db.is_user_x2(user_id)
    
    if x2_active_check and x2_until:
        try:
            from datetime import datetime, timezone
            x2_str = x2_until.replace('Z', '+00:00')
            if '+' not in x2_str and 'T' in x2_str:
                x2_str += '+00:00'
            x2_until_dt = datetime.fromisoformat(x2_str)
            
            if x2_until_dt.tzinfo is None:
                x2_until_dt = x2_until_dt.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            hours_left = int((x2_until_dt - now).total_seconds() / 3600)
            if hours_left > 0:
                text += f"⚡ <b>Статус x2 активен</b>\n"
                text += f"⏰ Осталось: {hours_left} часов\n\n"
            else:
                text += "⚡ <b>Статус x2:</b> Неактивен\n\n"
        except Exception as e:
            logger.error(f"Ошибка форматирования x2_until: {e}, значение: {x2_until}")
            if x2_active_check:
                text += f"⚡ <b>Статус x2 активен</b>\n\n"
            else:
                text += "⚡ <b>Статус x2:</b> Неактивен\n\n"
    else:
        text += "⚡ <b>Статус x2:</b> Неактивен\n\n"
    
    text += (
        "<blockquote>💡 За каждого приглашенного друга вы получаете +24 часа статуса x2.\n"
        "Пользователи с x2 получают 100% вакансий, обычные — 80%.</blockquote>"
    )
    
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(
            text="Поделиться ссылкой",
            url=f"https://t.me/share/url?url={referral_link}&text=Присоединяйся к FreelanceHub!"
        )
    )
    
    # Получаем фото для реферальной системы
    referral_photo = await db.get_referral_photo()
    
    # Отправляем сообщение с фото или без
    if referral_photo:
        # Проверяем длину caption (максимум 1024 символа)
        max_caption_length = 1024
        caption = text
        if len(caption) > max_caption_length:
            caption = truncate_html_safe(caption, max_caption_length)
        
        try:
            # Удаляем старое сообщение и отправляем новое с фото
            await callback.message.delete()
            await callback.message.answer_photo(
                photo=referral_photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard.as_markup()
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить фото реферальной системы: {e}")
            # Fallback: отправляем только текст
            try:
                await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
            except:
                await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
    else:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
    
    await callback.answer()


# =========================================
# ПРОВЕРКА ПОДПИСКИ (callback)
# =========================================

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery, bot: Bot):
    """Проверка подписки по нажатию кнопки"""
    user_id = callback.from_user.id
    
    is_subscribed = await check_channel_subscription(bot, user_id)
    
    if is_subscribed:
        # Обновляем статус
        await db.update_user_subscription(user_id, True)
        
        await callback.message.edit_text(
            "Подписка подтверждена.\n\nТеперь выберите направления — и можно начинать.",
        )
        
        # Показываем выбор категорий
        from keyboards.main import categories_keyboard
        await callback.message.answer(
            "Выберите направления:",
            reply_markup=categories_keyboard()
        )
        
        # Показываем главное меню
        await callback.message.answer(
            "\u00A0",
            reply_markup=main_menu_keyboard()
        )
    else:
        await callback.answer(
            "Подписка не найдена. Подпишитесь на канал и нажмите «Проверить».",
            show_alert=True
        )


# =========================================
# КОМАНДА /help И КНОПКА ПОМОЩЬ
# =========================================

@router.message(Command("help"))
@router.message(F.text == "Помощь")
async def cmd_help(message: Message):
    """FAQ + помощь по боту"""
    # Формируем полный FAQ текст
    faq_text = (
        "❓ <b>FAQ — Часто задаваемые вопросы</b>\n\n\n"
        "🔹 <b>Что такое FreelanceHub?</b>\n"
        "<blockquote>FreelanceHub — это Telegram-бот, который собирает и отправляет актуальные вакансии и заказы для фрилансеров из проверенных источников.</blockquote>\n\n"
        "🔹 <b>Как получать вакансии?</b>\n"
        "<blockquote>Подпишитесь на бота, выберите интересующие категории — и новые вакансии будут приходить автоматически.</blockquote>\n\n"
        "🔹 <b>Бесплатно ли пользоваться ботом?</b>\n"
        "<blockquote>На старте бот полностью бесплатный. В будущем появятся платные подписки с расширенными возможностями.</blockquote>\n\n"
        "🔹 <b>Какие категории доступны?</b>\n"
        "<blockquote>Дизайн, разработка, маркетинг, тексты, SMM, видео, менеджмент и другие направления фриланса.</blockquote>\n\n"
        "🔹 <b>Можно ли предложить свою вакансию?</b>\n"
        "<blockquote>Да. Вы можете отправить свою вакансию через бота, она пройдёт модерацию и будет опубликована.</blockquote>"
    )

    # Формируем клавиатуру с кнопкой "Оставить отзыв"
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    keyboard = InlineKeyboardBuilder()
    
    # Добавляем кнопку "Оставить отзыв" если настроен бот отзывов
    feedback_bot = config.channel.feedback_bot
    if feedback_bot:
        if feedback_bot.startswith("http"):
            feedback_link = feedback_bot
        elif feedback_bot.startswith("@"):
            feedback_link = f"https://t.me/{feedback_bot[1:]}"
        else:
            feedback_link = f"https://t.me/{feedback_bot}"
        
        keyboard.row(
            InlineKeyboardButton(
                text="Оставить отзыв",
                url=feedback_link
            )
        )
    
    reply_markup = keyboard.as_markup()
    
    # Проверяем есть ли FAQ фото
    faq_photo_id = await db.get_faq_photo()
    
    if faq_photo_id:
        # Отправляем фото с текстом FAQ в caption (одно сообщение)
        # Максимальная длина caption в Telegram - 1024 символа
        max_caption_length = 1024
        
        # Если текст длиннее лимита, обрезаем безопасно
        if len(faq_text) > max_caption_length:
            try:
                faq_text = truncate_html_safe(faq_text, max_caption_length)
            except Exception as e:
                logger.error(f"Ошибка обрезки HTML: {e}")
                # Fallback: убираем HTML и обрезаем как обычный текст
                import html
                plain_text = html.unescape(re.sub(r'<[^>]+>', '', faq_text))
                faq_text = plain_text[:max_caption_length - 3] + "..."
        
        try:
            await message.answer_photo(
                photo=faq_photo_id,
                caption=faq_text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить FAQ фото: {e}")
            # Fallback: отправляем только текст если фото не отправилось
            # Убираем HTML для безопасности
            try:
                await message.answer(faq_text, parse_mode="HTML", reply_markup=reply_markup)
            except:
                import html
                plain_text = html.unescape(re.sub(r'<[^>]+>', '', faq_text))
                await message.answer(plain_text, reply_markup=reply_markup)
    else:
        # Если фото нет - отправляем только текст
        await message.answer(faq_text, parse_mode="HTML", reply_markup=reply_markup)


# =========================================
# СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ
# =========================================

@router.message(Command("stats"))
@router.message(F.text == "Реферальная система")
async def cmd_referral_system(message: Message):
    """Показать реферальную систему"""
    # Используем существующую функцию cmd_ref
    await cmd_ref(message)


# =========================================
# ОБРАБОТКА НЕИЗВЕСТНЫХ СООБЩЕНИЙ
# =========================================

@router.message(F.text)
async def unknown_message(message: Message, bot: Bot):
    """Обработка неизвестных текстовых сообщений"""
    # Проверяем подписку
    is_subscribed = await check_channel_subscription(bot, message.from_user.id)
    
    if not is_subscribed:
        await message.answer(
            "Для доступа к вакансиям нужна подписка на официальный канал.\n\n"
            "Подпишитесь и нажмите «Проверить».",
            reply_markup=subscription_keyboard(config.channel.required_channel)
        )
        return
    
    await message.answer(
        "Команда не распознана. Используйте меню — так быстрее.",
        reply_markup=main_menu_keyboard()
    )



