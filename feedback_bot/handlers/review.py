"""
Обработчики для отправки отзывов.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db

logger = logging.getLogger(__name__)

router = Router()


class ReviewStates(StatesGroup):
    """Состояния для отправки отзыва"""
    waiting_for_text = State()
    waiting_for_rating = State()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Приветственное сообщение"""
    text = (
        "👋 <b>Добро пожаловать в бот отзывов FreelanceHub!</b>\n\n"
        "💬 Оставьте свой отзыв о работе бота, и за одобренный отзыв "
        "вы получите <b>+3 дня подписки на вакансии</b>!\n\n"
        "⚠️ Каждый пользователь может оставить только один отзыв.\n"
        "📝 Чтобы оставить отзыв, используйте команду /review"
    )
    
    await message.answer(text, parse_mode="HTML")


@router.message(Command("review"))
async def cmd_review(message: Message, state: FSMContext):
    """Начать процесс отправки отзыва"""
    user = message.from_user
    
    # Проверяем, не отправлял ли пользователь уже отзыв
    # Проверяем все отзывы (не только одобренные), чтобы не позволить оставить второй
    try:
        all_user_reviews = await db.get_user_reviews(user.id)
        if all_user_reviews:
            await message.answer(
                "❌ <b>Вы уже оставляли отзыв!</b>\n\n"
                "💡 Каждый пользователь может оставить только один отзыв.\n"
                "За одобренный отзыв вы получите <b>+3 дня подписки</b>.\n\n"
                "📋 Если ваш отзыв еще на модерации, дождитесь результата.",
                parse_mode="HTML"
            )
            return
    except Exception as e:
        logger.error(f"Ошибка проверки отзывов пользователя {user.id}: {e}")
        # Продолжаем, если ошибка проверки
    
    text = (
        "📝 <b>Оставить отзыв</b>\n\n"
        "Напишите ваш отзыв о работе бота FreelanceHub.\n"
        "Опишите что вам нравится, что можно улучшить, или просто поделитесь впечатлениями.\n\n"
        "💡 <b>Важно:</b> Отзыв пройдет модерацию. За одобренный отзыв вы получите <b>+3 дня подписки</b>!\n\n"
        "⚠️ Каждый пользователь может оставить только один отзыв.\n\n"
        "Для отмены — /cancel"
    )
    
    await state.set_state(ReviewStates.waiting_for_text)
    await message.answer(text, parse_mode="HTML")


@router.message(ReviewStates.waiting_for_text, F.text)
async def receive_review_text(message: Message, state: FSMContext):
    """Получение текста отзыва"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отправка отзыва отменена.")
        return
    
    text = message.text.strip()
    
    # Проверяем минимальную длину
    if len(text) < 10:
        await message.answer(
            "❌ Отзыв слишком короткий. Пожалуйста, напишите хотя бы 10 символов.\n\n"
            "Для отмены — /cancel"
        )
        return
    
    # Сохраняем текст отзыва
    await state.update_data(review_text=text)
    
    # Спрашиваем оценку (опционально)
    await state.set_state(ReviewStates.waiting_for_rating)
    await message.answer(
        "⭐ <b>Оценка (опционально)</b>\n\n"
        "Поставьте оценку от 1 до 5, или отправьте /skip чтобы пропустить.\n\n"
        "Для отмены — /cancel"
    )


@router.message(ReviewStates.waiting_for_rating, F.text)
async def receive_review_rating(message: Message, state: FSMContext):
    """Получение оценки отзыва"""
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отправка отзыва отменена.")
        return
    
    if message.text == "/skip":
        rating = None
    else:
        try:
            rating = int(message.text.strip())
            if rating < 1 or rating > 5:
                await message.answer(
                    "❌ Оценка должна быть от 1 до 5.\n\n"
                    "Отправьте число от 1 до 5, /skip чтобы пропустить, или /cancel для отмены."
                )
                return
        except ValueError:
            await message.answer(
                "❌ Пожалуйста, отправьте число от 1 до 5, /skip чтобы пропустить, или /cancel для отмены."
            )
            return
    
    # Получаем данные из состояния
    data = await state.get_data()
    review_text = data.get("review_text")
    
    if not review_text:
        await state.clear()
        await message.answer("❌ Ошибка: текст отзыва не найден. Начните заново с /review")
        return
    
    # Проверяем еще раз перед созданием (на случай если пользователь начал процесс раньше)
    user = message.from_user
    try:
        existing_reviews = await db.get_user_reviews(user.id)
        if existing_reviews:
            await state.clear()
            await message.answer(
                "❌ <b>Вы уже оставляли отзыв!</b>\n\n"
                "💡 Каждый пользователь может оставить только один отзыв.\n"
                "Если ваш отзыв еще на модерации, дождитесь результата.",
                parse_mode="HTML"
            )
            return
    except Exception as e:
        logger.error(f"Ошибка проверки отзывов перед созданием: {e}")
        # Продолжаем, если ошибка проверки
    
    # Создаем отзыв в БД
    review = await db.create_review(
        tg_id=user.id,
        text=review_text,
        username=user.username,
        first_name=user.first_name,
        rating=rating
    )
    
    if review:
        await state.clear()
        await message.answer(
            "✅ <b>Отзыв отправлен на модерацию!</b>\n\n"
            "📋 Ваш отзыв будет проверен администратором.\n"
            "После одобрения вы получите <b>+3 дня подписки на вакансии</b>.\n\n"
            "💡 Вы получите уведомление, когда отзыв будет рассмотрен."
        )
    else:
        await message.answer(
            "❌ Не удалось отправить отзыв. Попробуйте еще раз позже."
        )


@router.message(ReviewStates.waiting_for_text)
@router.message(ReviewStates.waiting_for_rating)
async def invalid_review_input(message: Message):
    """Некорректный ввод при ожидании отзыва"""
    if message.text == "/cancel":
        return
    
    await message.answer(
        "Пожалуйста, отправьте текст отзыва.\n\n"
        "Для отмены — /cancel"
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка"""
    text = (
        "📖 <b>Справка</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — Главное меню\n"
        "/review — Оставить отзыв\n"
        "/help — Эта справка\n\n"
        "<b>О системе отзывов:</b>\n"
        "💬 Оставьте отзыв о работе бота FreelanceHub.\n"
        "✨ За одобренный отзыв вы получите <b>+3 дня подписки на вакансии</b>.\n"
        "📋 Отзыв проходит модерацию перед одобрением.\n"
        "⚠️ Каждый пользователь может оставить только один отзыв."
    )
    
    await message.answer(text, parse_mode="HTML")

