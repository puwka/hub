"""
Основные обработчики для пользователей.
Старт, подписка, помощь.
"""

import logging
import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart

from config import config, CATEGORIES, REFERRAL_BONUS_DAYS, WELCOME_SUBSCRIPTION_DAYS
from utils.subscription import format_subscription_status_html
from database import db
from keyboards import main_menu_keyboard, subscription_keyboard
from utils.subscription_check import check_channel_subscription

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


async def _send_welcome_text(message: Message, welcome_text: str, inline_markup):
    """Отправить приветствие текстом (fallback без фото)."""
    try:
        return await message.answer(
            welcome_text,
            parse_mode="HTML",
            reply_markup=inline_markup,
        )
    except Exception:
        import html
        plain_text = html.unescape(re.sub(r"<[^>]+>", "", welcome_text))
        return await message.answer(
            plain_text,
            reply_markup=inline_markup,
        )


async def _send_welcome_message(message: Message, welcome_text: str, inline_markup):
    """Приветствие: фото + caption или только текст."""
    welcome_photo_id = await db.get_welcome_photo()
    if not welcome_photo_id:
        return await _send_welcome_text(message, welcome_text, inline_markup)

    max_caption_length = 1024
    caption = welcome_text
    if len(caption) > max_caption_length:
        caption = truncate_html_safe(caption, max_caption_length)

    try:
        return await message.answer_photo(
            photo=welcome_photo_id,
            caption=caption,
            parse_mode="HTML",
            reply_markup=inline_markup,
        )
    except Exception as e:
        logger.warning("Не удалось отправить фото приветствия: %s", e)
        if "wrong file identifier" in str(e).lower():
            await db.clear_welcome_photo()
            logger.info("Устаревший file_id фото приветствия удалён из БД")
        return await _send_welcome_text(message, welcome_text, inline_markup)


def _build_referral_message(referral_link: str, referral_count: int, subscription_until) -> str:
    text = (
        "🎁 <b>Реферальная система</b>\n\n"
        f"📋 <b>Ваша ссылка:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"👥 <b>Приглашено друзей:</b> {referral_count}\n\n"
    )
    text += format_subscription_status_html(subscription_until)
    text += (
        f"<blockquote>💡 За каждого приглашённого друга — "
        f"+{REFERRAL_BONUS_DAYS} день к подписке.\n"
        "Без активной подписки вакансии не приходят.</blockquote>"
    )
    return text


async def _send_referral_info(message: Message, referral_link: str, referral_count: int, subscription_until):
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    text = _build_referral_message(referral_link, referral_count, subscription_until)
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(
            text="Поделиться ссылкой",
            url=f"https://t.me/share/url?url={referral_link}&text=Присоединяйся к FreelanceHub!",
        )
    )
    markup = keyboard.as_markup()
    referral_photo = await db.get_referral_photo()

    if referral_photo:
        caption = truncate_html_safe(text, 1024) if len(text) > 1024 else text
        try:
            await message.answer_photo(
                photo=referral_photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
            return
        except Exception as e:
            logger.warning("Не удалось отправить фото реферальной системы: %s", e)

    await message.answer(text, parse_mode="HTML", reply_markup=markup)


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
    
    is_new_user = await db.get_user(user.id) is None

    # Создаем или получаем пользователя из БД
    db_user, referral_bonus_awarded = await db.get_or_create_user(
        tg_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        referred_by=referred_by
    )

    if referral_bonus_awarded and referred_by:
        friend_name = user.first_name or user.username or "новый пользователь"
        days_word = "день" if REFERRAL_BONUS_DAYS == 1 else "дня"
        try:
            await bot.send_message(
                referred_by,
                f"🎉 По вашей ссылке зарегистрировался <b>{friend_name}</b>!\n\n"
                f"🎁 Вам начислен +{REFERRAL_BONUS_DAYS} {days_word} к подписке.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("Не удалось уведомить реферера %s: %s", referred_by, e)
    
    # Проверяем подписку на канал
    subscription = await check_channel_subscription(bot, user.id)
    is_subscribed = subscription.subscribed
    
    if not subscription.bot_can_check:
        await message.answer(
            "Проверка подписки временно недоступна: бот не настроен для канала.\n"
            "Администратор уже получил уведомление."
        )
        return
    
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
        )
        if is_new_user:
            info_text += (
                f"🎁 Вам начислено <b>{WELCOME_SUBSCRIPTION_DAYS} дней подписки</b> — "
                "вакансии будут приходить автоматически.\n\n"
            )
        info_text += "🚀 Начните с выбора направлений, чтобы получать подходящие предложения."
        
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
        inline_markup = welcome_keyboard.as_markup()

        await _send_welcome_message(message, welcome_text, inline_markup)

        if not db_user or not db_user.get("categories"):
            from keyboards.main import categories_keyboard
            await message.answer(
                "Выберите направления, которые вам интересны. Можно выбрать несколько.",
                reply_markup=categories_keyboard(),
            )
            await message.answer(
                "Используйте меню ниже для навигации.",
                reply_markup=main_menu_keyboard(),
            )
        else:
            await message.answer(
                "Используйте меню ниже для навигации.",
                reply_markup=main_menu_keyboard(),
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
    subscription_until = stats.get("subscription_until")

    if not referral_code:
        referral_code = await db.create_referral_code(message.from_user.id)
        if not referral_code:
            await message.answer("❌ Ошибка: не удалось создать реферальный код")
            return

    bot_username = (await message.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    await _send_referral_info(message, referral_link, referral_count, subscription_until)


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
    subscription_until = stats.get("subscription_until")

    if not referral_code:
        referral_code = await db.create_referral_code(user_id)
        if not referral_code:
            await callback.answer("❌ Ошибка: не удалось создать реферальный код", show_alert=True)
            return

    bot_username = (await callback.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"

    try:
        await callback.message.delete()
    except Exception:
        pass

    await _send_referral_info(
        callback.message,
        referral_link,
        referral_count,
        subscription_until,
    )
    await callback.answer()


# =========================================
# ПРОВЕРКА ПОДПИСКИ (callback)
# =========================================

@router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery, bot: Bot):
    """Проверка подписки по нажатию кнопки"""
    user_id = callback.from_user.id
    
    subscription = await check_channel_subscription(bot, user_id)
    
    if not subscription.bot_can_check:
        await callback.answer(
            "Бот не может проверить подписку. Нужно добавить его админом канала.",
            show_alert=True,
        )
        return
    
    if subscription.subscribed:
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
        
        await callback.message.answer(
            "Используйте меню ниже для навигации.",
            reply_markup=main_menu_keyboard(),
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
        "<blockquote>Новым пользователям — 5 дней подписки бесплатно. "
        "Без активной подписки вакансии не приходят.</blockquote>\n\n"
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
    subscription = await check_channel_subscription(bot, message.from_user.id)
    
    if not subscription.subscribed:
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



