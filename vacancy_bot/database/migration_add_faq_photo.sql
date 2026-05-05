-- Миграция: фото для FAQ (раздел «Помощь»)
-- Выполните в Supabase SQL Editor

CREATE TABLE IF NOT EXISTS faq_photo (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) NOT NULL,
    file_unique_id VARCHAR(255),
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    uploaded_by BIGINT
);




