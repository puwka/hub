"""
Обработчики подачи и модерации пользовательских вакансий.

Флоу:
  /add → текст → категория → контакт → превью → модерация → одобрение/отклонение
"""

import logging
import re

from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import CATEGORIES, MODERATION_CHAT, ADMIN_IDS, VACANCY_BOT_USERNAME
from database import db

logger = logging.getLogger(__name__)

router = Router()

MIN_TEXT_LENGTH = 50


# ─── FSM ─────────────────────────────────────────────────────────

class AddVacancy(StatesGroup):
    waiting_text = State()
    waiting_category = State()
    waiting_contact = State()
    confirm = State()


# ─── Клавиатуры ──────────────────────────────────────────────────

def _categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat_id, cat in CATEGORIES.items():
        builder.row(
            InlineKeyboardButton(
                text=cat["name"],
                callback_data=f"cat:{cat_id}",
            )
        )
    return builder.as_markup()


def _confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Отправить", callback_data="vacancy:send"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="vacancy:cancel"),
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить текст", callback_data="vacancy:edit_text"),
        InlineKeyboardButton(text="🔄 Изменить категорию", callback_data="vacancy:edit_cat"),
    )
    return builder.as_markup()


def _moderation_keyboard(vacancy_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Принять",
            callback_data=f"uv_mod:approve:{vacancy_id}",
        ),
        InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=f"uv_mod:reject:{vacancy_id}",
        ),
    )
    return builder.as_markup()


# ─── /start ──────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "👋 <b>Добро пожаловать в бот подачи вакансий FreelanceHub!</b>\n\n"
        "📝 Здесь вы можете опубликовать свою вакансию.\n"
        "После модерации она будет разослана нашим подписчикам.\n\n"
        "<b>Как это работает:</b>\n"
        "1️⃣ Отправьте текст вакансии\n"
        "2️⃣ Выберите направление\n"
        "3️⃣ Укажите контакт для отклика\n"
        "4️⃣ Подтвердите отправку\n\n"
        "➡️ Чтобы начать — нажмите /add"
    )
    await message.answer(text, parse_mode="HTML")


# ─── /add — начало подачи ────────────────────────────────────────

@router.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "📝 <b>Подача вакансии</b>\n\n"
        "Отправьте текст вакансии.\n"
        "Опишите задачу, требования и условия.\n\n"
        f"⚠️ Минимум <b>{MIN_TEXT_LENGTH}</b> символов.\n\n"
        "Для отмены — /cancel"
    )
    await state.set_state(AddVacancy.waiting_text)
    await message.answer(text, parse_mode="HTML")


# ─── /cancel ─────────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного процесса для отмены.")
        return
    await state.clear()
    await message.answer(
        "❌ Подача вакансии отменена.\n\n"
        "Чтобы начать заново — /add",
    )


# ─── Шаг 1: текст вакансии ──────────────────────────────────────

@router.message(AddVacancy.waiting_text, F.text)
async def receive_text(message: Message, state: FSMContext):
    if message.text.startswith("/"):
        return

    text = message.text.strip()
    if len(text) < MIN_TEXT_LENGTH:
        await message.answer(
            f"❌ Текст слишком короткий ({len(text)} символов).\n"
            f"Минимум — <b>{MIN_TEXT_LENGTH}</b> символов.\n\n"
            "Отправьте текст заново или /cancel для отмены.",
            parse_mode="HTML",
        )
        return

    await state.update_data(vacancy_text=text)
    await state.set_state(AddVacancy.waiting_category)
    await message.answer(
        "✅ Текст принят!\n\n"
        "📂 <b>Выберите направление вакансии:</b>",
        parse_mode="HTML",
        reply_markup=_categories_keyboard(),
    )


# ─── Шаг 2: выбор категории ─────────────────────────────────────

@router.callback_query(AddVacancy.waiting_category, F.data.startswith("cat:"))
async def receive_category(callback: CallbackQuery, state: FSMContext):
    cat_id = callback.data.split(":", 1)[1]
    if cat_id not in CATEGORIES:
        await callback.answer("Неизвестная категория", show_alert=True)
        return

    await state.update_data(category=cat_id)
    await state.set_state(AddVacancy.waiting_contact)

    await callback.message.edit_text(
        f"✅ Направление: <b>{CATEGORIES[cat_id]['name']}</b>\n\n"
        "📞 <b>Укажите контакт для отклика:</b>\n\n"
        "Отправьте @username, телефон, email или ссылку.\n"
        "Кандидаты будут связываться с вами по этому контакту.\n\n"
        "Для отмены — /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Шаг 3: контакт ─────────────────────────────────────────────

_CONTACT_RE = re.compile(
    r"@\w{3,}|"                                       # @username
    r"\+?\d[\d\s\-()]{8,}\d|"                         # телефон
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}|" # email
    r"https?://\S+|t\.me/\S+",                        # ссылка
    re.IGNORECASE,
)


@router.message(AddVacancy.waiting_contact, F.text)
async def receive_contact(message: Message, state: FSMContext):
    if message.text.startswith("/"):
        return

    contact = message.text.strip()

    if not _CONTACT_RE.search(contact):
        await message.answer(
            "❌ Не распознан контакт.\n\n"
            "Отправьте @username, номер телефона, email или ссылку.\n\n"
            "Для отмены — /cancel",
        )
        return

    await state.update_data(contact=contact)
    await state.set_state(AddVacancy.confirm)

    data = await state.get_data()
    preview = _format_preview(data)

    await message.answer(
        f"📋 <b>Превью вакансии</b>\n\n{preview}\n\n"
        "Всё верно? Отправляем на модерацию?",
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(),
    )


# ─── Превью ──────────────────────────────────────────────────────

def _format_preview(data: dict) -> str:
    cat_id = data.get("category", "other")
    cat = CATEGORIES.get(cat_id, CATEGORIES["other"])
    text = data.get("vacancy_text", "")
    contact = data.get("contact", "")

    # Обрезаем для превью если очень длинный
    display_text = text if len(text) <= 1500 else text[:1500] + "…"

    return (
        f"📂 <b>Направление:</b> {cat['name']}\n"
        f"📞 <b>Контакт:</b> {contact}\n\n"
        f"<blockquote>{display_text}</blockquote>"
    )


# ─── Подтверждение / Редактирование ──────────────────────────────

@router.callback_query(AddVacancy.confirm, F.data == "vacancy:send")
async def confirm_send(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user = callback.from_user

    # Создаём вакансию в БД
    vacancy = await db.create_user_vacancy(
        tg_id=user.id,
        username=user.username,
        text=data["vacancy_text"],
        category=data["category"],
        contact=data["contact"],
    )

    if not vacancy:
        await callback.message.edit_text(
            "❌ Ошибка при сохранении вакансии. Попробуйте позже.",
        )
        await state.clear()
        await callback.answer()
        return

    vacancy_id = vacancy["id"]

    # Отправляем в чат модерации
    mod_text = _format_moderation_message(vacancy, user)
    try:
        mod_chat = int(MODERATION_CHAT)
        await bot.send_message(
            chat_id=mod_chat,
            text=mod_text,
            parse_mode="HTML",
            reply_markup=_moderation_keyboard(vacancy_id),
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"Ошибка отправки в модерацию: {e}")

    await callback.message.edit_text(
        "✅ <b>Вакансия отправлена на модерацию!</b>\n\n"
        "📋 Администратор проверит вашу вакансию.\n"
        "Вы получите уведомление о результате.\n\n"
        "➡️ Чтобы подать ещё одну — /add",
        parse_mode="HTML",
    )
    await state.clear()
    await callback.answer("Отправлено!")


@router.callback_query(AddVacancy.confirm, F.data == "vacancy:cancel")
async def confirm_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Подача вакансии отменена.\n\n"
        "Чтобы начать заново — /add",
    )
    await callback.answer()


@router.callback_query(AddVacancy.confirm, F.data == "vacancy:edit_text")
async def edit_text(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddVacancy.waiting_text)
    await callback.message.edit_text(
        "✏️ Отправьте новый текст вакансии.\n\n"
        f"⚠️ Минимум <b>{MIN_TEXT_LENGTH}</b> символов.\n"
        "Для отмены — /cancel",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(AddVacancy.confirm, F.data == "vacancy:edit_cat")
async def edit_category(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AddVacancy.waiting_category)
    await callback.message.edit_text(
        "🔄 <b>Выберите новое направление:</b>",
        parse_mode="HTML",
        reply_markup=_categories_keyboard(),
    )
    await callback.answer()


# ─── Модерация ───────────────────────────────────────────────────

def _format_moderation_message(vacancy: dict, user) -> str:
    cat_id = vacancy.get("category", "other")
    cat = CATEGORIES.get(cat_id, CATEGORIES["other"])
    text = vacancy.get("text", "")
    contact = vacancy.get("contact", "")
    username = f"@{user.username}" if user.username else f"ID: {user.id}"

    if len(text) > 3000:
        text = text[:3000] + "…"

    return (
        f"📥 <b>Новая вакансия от пользователя</b>\n\n"
        f"👤 <b>Автор:</b> {username}\n"
        f"📂 <b>Направление:</b> {cat['name']}\n"
        f"📞 <b>Контакт:</b> {contact}\n"
        f"🆔 <b>ID:</b> #{vacancy['id']}\n\n"
        f"<blockquote>{text}</blockquote>"
    )


@router.callback_query(F.data.startswith("uv_mod:"))
async def moderation_callback(callback: CallbackQuery, bot: Bot):
    """Обработка кнопок модерации."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Ошибка", show_alert=True)
        return

    action = parts[1]        # approve / reject
    vacancy_id = int(parts[2])
    moderator = callback.from_user

    # Проверяем права
    if moderator.id not in ADMIN_IDS:
        await callback.answer("⛔ У вас нет прав модерации.", show_alert=True)
        return

    vacancy = await db.get_user_vacancy(vacancy_id)
    if not vacancy:
        await callback.answer("Вакансия не найдена.", show_alert=True)
        return

    if vacancy.get("status") != "pending":
        await callback.answer("Вакансия уже обработана.", show_alert=True)
        return

    author_tg_id = vacancy["tg_id"]

    if action == "approve":
        ok = await db.approve_user_vacancy(vacancy_id, moderator.id)
        if ok:
            # Обновляем сообщение модерации
            await callback.message.edit_text(
                callback.message.text + f"\n\n✅ <b>ОДОБРЕНО</b> модератором "
                f"@{moderator.username or moderator.id}",
                parse_mode="HTML",
            )
            # Уведомляем автора
            try:
                await bot.send_message(
                    chat_id=author_tg_id,
                    text=(
                        "✅ <b>Ваша вакансия одобрена!</b>\n\n"
                        "Она будет разослана подписчикам "
                        f"@{VACANCY_BOT_USERNAME}.\n\n"
                        "➡️ Чтобы подать ещё одну — /add"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления автора {author_tg_id}: {e}")

            await callback.answer("✅ Одобрено!")
        else:
            await callback.answer("Ошибка при одобрении.", show_alert=True)

    elif action == "reject":
        ok = await db.reject_user_vacancy(vacancy_id, moderator.id)
        if ok:
            await callback.message.edit_text(
                callback.message.text + f"\n\n❌ <b>ОТКЛОНЕНО</b> модератором "
                f"@{moderator.username or moderator.id}",
                parse_mode="HTML",
            )
            try:
                await bot.send_message(
                    chat_id=author_tg_id,
                    text=(
                        "❌ <b>Ваша вакансия отклонена.</b>\n\n"
                        "Возможные причины:\n"
                        "• Недостаточно информации\n"
                        "• Не соответствует формату\n"
                        "• Спам или реклама\n\n"
                        "➡️ Вы можете подать вакансию заново — /add"
                    ),
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления автора {author_tg_id}: {e}")

            await callback.answer("❌ Отклонено!")
        else:
            await callback.answer("Ошибка при отклонении.", show_alert=True)


# ─── /help ───────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>Справка</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — Главное меню\n"
        "/add — Подать вакансию\n"
        "/cancel — Отменить подачу\n"
        "/help — Эта справка\n\n"
        "<b>Как подать вакансию:</b>\n"
        "1️⃣ Напишите /add\n"
        "2️⃣ Отправьте описание вакансии\n"
        "3️⃣ Выберите направление\n"
        "4️⃣ Укажите контакт для отклика\n"
        "5️⃣ Проверьте превью и отправьте\n\n"
        "📋 Вакансия пройдёт модерацию.\n"
        "После одобрения она будет разослана подписчикам "
        f"@{VACANCY_BOT_USERNAME}."
    )
    await message.answer(text, parse_mode="HTML")


# ─── Некорректный ввод ───────────────────────────────────────────

@router.message(AddVacancy.waiting_text)
async def invalid_text(message: Message):
    await message.answer(
        "Пожалуйста, отправьте текст вакансии.\n"
        "Для отмены — /cancel",
    )


@router.message(AddVacancy.waiting_category)
async def invalid_category(message: Message):
    await message.answer(
        "Пожалуйста, выберите направление из кнопок выше.\n"
        "Для отмены — /cancel",
    )


@router.message(AddVacancy.waiting_contact)
async def invalid_contact(message: Message):
    await message.answer(
        "Пожалуйста, отправьте контакт (@username, телефон, email или ссылку).\n"
        "Для отмены — /cancel",
    )
