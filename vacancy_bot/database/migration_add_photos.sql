-- Миграция: добавление поддержки фото в вакансиях

-- Добавляем поля для фото в таблицу vacancies
ALTER TABLE vacancies 
ADD COLUMN IF NOT EXISTS has_photo BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS photo_file_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS photo_message_id BIGINT;

-- Таблица для дефолтного фото
CREATE TABLE IF NOT EXISTS default_photo (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(255) NOT NULL,
    file_unique_id VARCHAR(255),
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    uploaded_by BIGINT  -- Telegram ID админа
);

