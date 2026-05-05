"""
Обработчики добавления вакансий пользователями.
Форма: категория -> текст -> контакт -> подтверждение
"""

import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import CATEGORIES, config
from database import db
from keyboards import (
    main_menu_keyboard, 
    category_select_keyboard,
    confirm_keyboard,
    back_keyboard
)
from keyboards.main import categories_keyboard

logger = logging.getLogger(__name__)

router = Router()


# =========================================
# FSM СОСТОЯНИЯ
# =========================================

class AddVacancyStates(StatesGroup):
    """Состояния для добавления вакансии"""
    waiting_for_category = State()
    waiting_for_text = State()
    waiting_for_contact = State()
    waiting_for_confirm = State()


# =========================================
# НАЧАЛО ДОБАВЛЕНИЯ ВАКАНСИИ
# =========================================

@router.message(Command("add_vacancy"))
@router.message(F.text == "Добавить вакансию")
async def cmd_add_vacancy(message: Message, state: FSMContext):
    """Отправить ссылку на бота для добавления вакансий"""
    
    # Проверяем подписку
    user = await db.get_user(message.from_user.id)
    if not user or not user.get("is_subscribed"):
        from keyboards import subscription_keyboard
        await message.answer(
            f"📢 Для добавления вакансий подпишись на канал "
            f"{config.channel.required_channel}",
            reply_markup=subscription_keyboard(config.channel.required_channel)
        )
        return
    
    # Получаем ссылку на бота добавления вакансий
    add_vacancy_bot = config.channel.add_vacancy_bot
    
    if not add_vacancy_bot:
        await message.answer(
            "❌ Бот для добавления вакансий пока не настроен.\n"
            "Обратитесь к администратору."
        )
        return
    
    # Формируем ссылку (может быть username или полная ссылка)
    if add_vacancy_bot.startswith("http"):
        bot_link = add_vacancy_bot
    elif add_vacancy_bot.startswith("@"):
        bot_link = f"https://t.me/{add_vacancy_bot[1:]}"
    else:
        bot_link = f"https://t.me/{add_vacancy_bot}"
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(
            text="Перейти к боту",
            url=bot_link
        )
    )
    
    await message.answer(
        "Для добавления вакансии перейдите в специального бота.\n\n"
        "Там вы сможете разместить вакансию, которая пройдёт модерацию и будет отправлена подписчикам.",
        reply_markup=keyboard.as_markup()
    )


# =========================================
# ВЫБОР КАТЕГОРИИ
# =========================================

@router.callback_query(
    AddVacancyStates.waiting_for_category,
    F.data.startswith("select_cat:")
)
async def select_category(callback: CallbackQuery, state: FSMContext):
    """Выбор категории для вакансии"""
    category_id = callback.data.split(":")[1]
    
    if category_id not in CATEGORIES:
        await callback.answer("❌ Неизвестная категория")
        return
    
    # Сохраняем категорию
    await state.update_data(category=category_id)
    await state.set_state(AddVacancyStates.waiting_for_text)
    
    category_name = CATEGORIES[category_id]["name"]
    
    await callback.message.edit_text(
        f"Направление: {category_name}\n\n"
        "Шаг 2/4 — описание.\n"
        "Напишите кратко и по делу: задачи, условия, сроки.",
        parse_mode="Markdown",
        reply_markup=back_keyboard("cancel_vacancy")
    )
    
    await callback.answer()


# =========================================
# ВВОД ТЕКСТА ВАКАНСИИ
# =========================================

@router.message(AddVacancyStates.waiting_for_text, F.text)
async def receive_vacancy_text(message: Message, state: FSMContext):
    """Получение текста вакансии"""
    text = message.text.strip()
    
    # Проверка минимальной длины
    if len(text) < 50:
        await message.answer(
            "Слишком коротко.\n"
            "Добавьте детали: задача, формат, сроки, оплата."
        )
        return
    
    # Проверка максимальной длины
    if len(text) > 4000:
        await message.answer(
            "Слишком длинный текст.\n"
            "Сократите описание до 4000 символов."
        )
        return
    
    # Сохраняем текст
    await state.update_data(text=text)
    await state.set_state(AddVacancyStates.waiting_for_contact)
    
    await message.answer(
        "Шаг 3/4 — контакты.\n"
        "Укажите, как с вами связаться: @username, почта или ссылка.",
        reply_markup=back_keyboard("cancel_vacancy")
    )


# =========================================
# ВВОД КОНТАКТА
# =========================================

@router.message(AddVacancyStates.waiting_for_contact, F.text)
async def receive_contact(message: Message, state: FSMContext):
    """Получение контактных данных"""
    contact = message.text.strip()
    
    # Простая проверка
    if len(contact) < 3:
        await message.answer("Укажите корректные контактные данные.")
        return
    
    if len(contact) > 200:
        await message.answer("Слишком длинные контактные данные (до 200 символов).")
        return
    
    # Сохраняем контакт
    await state.update_data(contact=contact)
    await state.set_state(AddVacancyStates.waiting_for_confirm)
    
    # Получаем все данные для превью
    data = await state.get_data()
    category_name = CATEGORIES[data["category"]]["name"]
    
    preview = (
        "Проверьте перед отправкой:\n\n"
        f"Направление: {category_name}\n"
        f"Контакт: {contact}\n\n"
        f"{data['text'][:500]}{'...' if len(data['text']) > 500 else ''}\n\n"
        "Отправить на модерацию?"
    )
    
    await message.answer(
        preview,
        parse_mode="Markdown",
        reply_markup=confirm_keyboard("vacancy_confirm")
    )


# =========================================
# ПОДТВЕРЖДЕНИЕ ПУБЛИКАЦИИ
# =========================================

@router.callback_query(
    AddVacancyStates.waiting_for_confirm,
    F.data == "vacancy_confirm:yes"
)
async def confirm_vacancy(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и сохранение вакансии"""
    data = await state.get_data()
    user = callback.from_user
    
    # Сохраняем в БД
    vacancy = await db.create_user_vacancy(
        tg_id=user.id,
        username=user.username,
        text=data["text"],
        category=data["category"],
        contact=data["contact"]
    )
    
    if vacancy:
        await callback.message.edit_text(
            "Заявка отправлена на модерацию.\n"
            "Обычно это занимает немного времени.\n\n"
            "Мы уведомим вас о результате.",
            parse_mode="Markdown"
        )
        
        # Уведомляем админов
        await notify_admins_new_vacancy(callback.bot, vacancy, data)
        
        await callback.answer("✅ Вакансия отправлена!")
    else:
        await callback.message.edit_text(
            "Не удалось отправить заявку.\n"
            "Попробуйте ещё раз чуть позже."
        )
        await callback.answer("Ошибка", show_alert=True)
    
    await state.clear()


@router.callback_query(
    AddVacancyStates.waiting_for_confirm,
    F.data == "vacancy_confirm:no"
)
async def cancel_vacancy_confirm(callback: CallbackQuery, state: FSMContext):
    """Отмена на этапе подтверждения"""
    await state.clear()
    
    await callback.message.edit_text(
        "Отправка отменена. Вакансия не сохранена."
    )
    
    await callback.answer("Готово")


# =========================================
# ОТМЕНА НА ЛЮБОМ ЭТАПЕ
# =========================================

@router.callback_query(F.data == "cancel_vacancy")
async def cancel_vacancy(callback: CallbackQuery, state: FSMContext):
    """Отмена добавления вакансии"""
    await state.clear()
    
    await callback.message.edit_text(
        "Добавление отменено."
    )
    
    await callback.message.answer(
        "\u00A0",
        reply_markup=main_menu_keyboard()
    )
    
    await callback.answer("Готово")


# =========================================
# УВЕДОМЛЕНИЕ АДМИНОВ
# =========================================

async def notify_admins_new_vacancy(bot: Bot, vacancy: dict, data: dict):
    """Уведомить админов о новой вакансии на модерацию"""
    from keyboards.main import moderation_keyboard
    
    category_name = CATEGORIES[data["category"]]["name"]
    
    text = (
        "Новая вакансия на модерацию\n\n"
        f"Направление: {category_name}\n"
        f"Автор: @{vacancy.get('username') or vacancy['tg_id']}\n\n"
        f"{data['text'][:1000]}{'...' if len(data['text']) > 1000 else ''}\n\n"
        f"Контакт: {data['contact']}"
    )
    
    for admin_id in config.admin.ids:
        try:
            await bot.send_message(
                admin_id,
                text,
                parse_mode="Markdown",
                reply_markup=moderation_keyboard(vacancy["id"])
            )
        except Exception as e:
            logger.error(f"Ошибка уведомления админа {admin_id}: {e}")



