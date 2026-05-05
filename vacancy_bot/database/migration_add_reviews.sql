-- Миграция: система отзывов
-- Выполните в Supabase SQL Editor

-- Таблица отзывов
CREATE TABLE IF NOT EXISTS reviews (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT NOT NULL,  -- Telegram ID пользователя, оставившего отзыв
    username VARCHAR(255),
    first_name VARCHAR(255),
    text TEXT NOT NULL,  -- Текст отзыва
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),  -- Оценка от 1 до 5 (опционально)
    status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected
    moderator_id BIGINT,  -- Кто модерировал
    moderated_at TIMESTAMPTZ,  -- Когда промодерировали
    rejection_reason TEXT,  -- Причина отклонения
    x2_awarded BOOLEAN DEFAULT FALSE,  -- Было ли начислено x2
    x2_awarded_at TIMESTAMPTZ,  -- Когда начислено x2
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для поиска по статусу
CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);

-- Индекс для поиска по пользователю
CREATE INDEX IF NOT EXISTS idx_reviews_tg_id ON reviews(tg_id);

-- Индекс для поиска необработанных отзывов
CREATE INDEX IF NOT EXISTS idx_reviews_pending ON reviews(status) WHERE status = 'pending';

