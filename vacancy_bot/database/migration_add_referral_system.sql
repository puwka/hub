-- Миграция: реферальная система
-- Выполните в Supabase SQL Editor

-- Таблица рефералов
CREATE TABLE IF NOT EXISTS referrals (
    id BIGSERIAL PRIMARY KEY,
    referrer_id BIGINT NOT NULL,  -- ID пользователя, который пригласил
    referred_id BIGINT NOT NULL UNIQUE,  -- ID приглашенного пользователя
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (referrer_id) REFERENCES users(tg_id) ON DELETE CASCADE,
    FOREIGN KEY (referred_id) REFERENCES users(tg_id) ON DELETE CASCADE
);

-- Добавляем колонки в таблицу users для реферальной системы
ALTER TABLE users
ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20) UNIQUE,
ADD COLUMN IF NOT EXISTS x2_until TIMESTAMPTZ,  -- До какого времени действует x2 статус
ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0;  -- Количество приглашенных

-- Создаем индекс для быстрого поиска по referral_code
CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code);

-- Создаем индекс для быстрого поиска рефералов
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id);

