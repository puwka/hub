-- ============================================
-- МИГРАЦИЯ: система подписки на вакансии
-- Выполнить в Supabase SQL Editor (один раз)
-- ============================================
--
-- В коде бота подписка хранится в колонке users.x2_until
-- (историческое имя; это дата окончания подписки на вакансии).
--
-- Логика:
--   - новый пользователь: +5 дней (бот при регистрации)
--   - реферал: +1 день
--   - одобренный отзыв: +3 дня
--   - без активной подписки вакансии не рассылаются
-- ============================================


-- ============================================
-- 1. РЕФЕРАЛЬНАЯ СИСТЕМА (если ещё не применена)
-- ============================================

CREATE TABLE IF NOT EXISTS referrals (
    id BIGSERIAL PRIMARY KEY,
    referrer_id BIGINT NOT NULL,
    referred_id BIGINT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (referrer_id) REFERENCES users(tg_id) ON DELETE CASCADE,
    FOREIGN KEY (referred_id) REFERENCES users(tg_id) ON DELETE CASCADE
);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20) UNIQUE,
    ADD COLUMN IF NOT EXISTS x2_until TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_users_referral_code ON users(referral_code);
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals(referred_id);

-- Индекс для поиска пользователей с активной подпиской
CREATE INDEX IF NOT EXISTS idx_users_subscription_active
    ON users(x2_until)
    WHERE x2_until IS NOT NULL;

COMMENT ON COLUMN users.x2_until IS
    'Дата окончания подписки на вакансии (поле legacy, имя x2_until)';


-- ============================================
-- 2. ОТЗЫВЫ (если ещё не применена)
-- ============================================

CREATE TABLE IF NOT EXISTS reviews (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    text TEXT NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    status VARCHAR(20) DEFAULT 'pending',
    moderator_id BIGINT,
    moderated_at TIMESTAMPTZ,
    rejection_reason TEXT,
    x2_awarded BOOLEAN DEFAULT FALSE,
    x2_awarded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews(status);
CREATE INDEX IF NOT EXISTS idx_reviews_tg_id ON reviews(tg_id);
CREATE INDEX IF NOT EXISTS idx_reviews_pending ON reviews(status) WHERE status = 'pending';


-- ============================================
-- 3. НОРМАЛИЗАЦИЯ ДАННЫХ
-- ============================================

UPDATE users
SET referral_count = 0
WHERE referral_count IS NULL;


-- ============================================
-- 4. ПОДПИСКА ДЛЯ СУЩЕСТВУЮЩИХ ПОЛЬЗОВАТЕЛЕЙ
-- ============================================

-- 4a. Никогда не имели подписки — дать 5 дней (как новому пользователю)
UPDATE users
SET x2_until = NOW() + INTERVAL '5 days'
WHERE x2_until IS NULL;

-- 4b. ОПЦИОНАЛЬНО: продлить истёкшую подписку ещё на 5 дней
-- (раскомментируйте, если нужно «переехать» всех на новую систему)
-- UPDATE users
-- SET x2_until = NOW() + INTERVAL '5 days'
-- WHERE x2_until IS NOT NULL AND x2_until < NOW();


-- ============================================
-- 5. ПРОВЕРКА ПОСЛЕ МИГРАЦИИ
-- ============================================

-- Сводка по подпискам
SELECT
    COUNT(*) AS total_users,
    COUNT(*) FILTER (WHERE x2_until IS NOT NULL AND x2_until > NOW()) AS active_subscription,
    COUNT(*) FILTER (WHERE x2_until IS NULL) AS never_had_subscription,
    COUNT(*) FILTER (WHERE x2_until IS NOT NULL AND x2_until <= NOW()) AS expired_subscription
FROM users;

-- Пользователи с активной подпиской (им будут приходить вакансии)
SELECT
    tg_id,
    username,
    first_name,
    x2_until,
    ROUND(EXTRACT(EPOCH FROM (x2_until - NOW())) / 86400, 1) AS days_left
FROM users
WHERE x2_until > NOW()
ORDER BY x2_until DESC
LIMIT 50;

-- Пользователи БЕЗ подписки (вакансии не придут)
SELECT
    tg_id,
    username,
    first_name,
    x2_until
FROM users
WHERE x2_until IS NULL OR x2_until <= NOW()
ORDER BY created_at DESC
LIMIT 50;


-- ============================================
-- 6. РУЧНЫЕ КОМАНДЫ (примеры)
-- ============================================

-- Дать подписку конкретному пользователю (замените TG_ID)
-- UPDATE users
-- SET x2_until = GREATEST(COALESCE(x2_until, NOW()), NOW()) + INTERVAL '30 days'
-- WHERE tg_id = 1001949438;

-- Продлить подписку на N дней для всех с активной подпиской
-- UPDATE users
-- SET x2_until = x2_until + INTERVAL '7 days'
-- WHERE x2_until > NOW();
