-- ============================================
-- СХЕМА БАЗЫ ДАННЫХ ДЛЯ VACANCY BOT
-- Выполнить в Supabase SQL Editor
-- ============================================

-- ============================================
-- 1. ТАБЛИЦА ПОЛЬЗОВАТЕЛЕЙ
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    categories TEXT[] DEFAULT '{}',  -- Массив выбранных категорий
    is_subscribed BOOLEAN DEFAULT FALSE,  -- Подписан ли на обязательный канал
    is_active BOOLEAN DEFAULT TRUE,  -- Активен ли пользователь
    is_banned BOOLEAN DEFAULT FALSE,  -- Заблокирован ли
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для быстрого поиска по tg_id
CREATE INDEX IF NOT EXISTS idx_users_tg_id ON users(tg_id);

-- Индекс для поиска активных пользователей по категориям
CREATE INDEX IF NOT EXISTS idx_users_categories ON users USING GIN(categories);


-- ============================================
-- 2. ТАБЛИЦА ВАКАНСИЙ (из парсинга)
-- ============================================
CREATE TABLE IF NOT EXISTS vacancies (
    id BIGSERIAL PRIMARY KEY,
    text TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    source VARCHAR(255) NOT NULL,  -- @channel или название группы
    source_message_id BIGINT,  -- ID сообщения в источнике
    text_hash VARCHAR(64) UNIQUE NOT NULL,  -- SHA256 хеш для дедупликации
    is_sent BOOLEAN DEFAULT FALSE,  -- Была ли разослана
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для поиска неотправленных вакансий по категории
CREATE INDEX IF NOT EXISTS idx_vacancies_category_sent ON vacancies(category, is_sent);

-- Индекс для проверки дубликатов
CREATE INDEX IF NOT EXISTS idx_vacancies_hash ON vacancies(text_hash);


-- ============================================
-- 3. ТАБЛИЦА ОТПРАВЛЕННЫХ ВАКАНСИЙ
-- Связь many-to-many между users и vacancies
-- ============================================
CREATE TABLE IF NOT EXISTS sent_vacancies (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vacancy_id BIGINT NOT NULL REFERENCES vacancies(id) ON DELETE CASCADE,
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, vacancy_id)  -- Каждую вакансию отправляем пользователю только раз
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_sent_vacancies_user ON sent_vacancies(user_id);
CREATE INDEX IF NOT EXISTS idx_sent_vacancies_vacancy ON sent_vacancies(vacancy_id);


-- ============================================
-- 4. ТАБЛИЦА ВАКАНСИЙ ОТ ПОЛЬЗОВАТЕЛЕЙ
-- ============================================
CREATE TABLE IF NOT EXISTS user_vacancies (
    id BIGSERIAL PRIMARY KEY,
    tg_id BIGINT NOT NULL,  -- Telegram ID автора
    username VARCHAR(255),
    text TEXT NOT NULL,
    category VARCHAR(50) NOT NULL,
    contact VARCHAR(500) NOT NULL,  -- Контактные данные
    status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected
    moderator_id BIGINT,  -- Кто модерировал
    moderated_at TIMESTAMPTZ,
    rejection_reason TEXT,  -- Причина отклонения
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для поиска по статусу
CREATE INDEX IF NOT EXISTS idx_user_vacancies_status ON user_vacancies(status);


-- ============================================
-- 5. ТАБЛИЦА ИСТОЧНИКОВ ПАРСИНГА
-- ============================================
CREATE TABLE IF NOT EXISTS parse_sources (
    id BIGSERIAL PRIMARY KEY,
    source_type VARCHAR(20) NOT NULL,  -- channel, group
    source_id VARCHAR(255) NOT NULL,  -- @channel или chat_id
    title VARCHAR(255),  -- Название канала/группы
    is_active BOOLEAN DEFAULT TRUE,
    last_parsed_at TIMESTAMPTZ,
    last_message_id BIGINT DEFAULT 0,  -- Последнее обработанное сообщение
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id)
);


-- ============================================
-- 6. ТАБЛИЦА ЛОГОВ РАССЫЛКИ
-- Для контроля rate-limit
-- ============================================
CREATE TABLE IF NOT EXISTS send_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для подсчета сообщений за период
CREATE INDEX IF NOT EXISTS idx_send_logs_user_time ON send_logs(user_id, sent_at);


-- ============================================
-- 7. ТАБЛИЦА СТАТИСТИКИ
-- ============================================
CREATE TABLE IF NOT EXISTS stats (
    id BIGSERIAL PRIMARY KEY,
    date DATE UNIQUE NOT NULL,
    new_users INT DEFAULT 0,
    vacancies_parsed INT DEFAULT 0,
    vacancies_sent INT DEFAULT 0,
    user_vacancies_submitted INT DEFAULT 0,
    user_vacancies_approved INT DEFAULT 0
);


-- ============================================
-- ФУНКЦИИ И ТРИГГЕРЫ
-- ============================================

-- Функция для автообновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггер для users
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================
-- RLS (Row Level Security) - опционально
-- ============================================
-- Если нужна дополнительная безопасность на уровне Supabase

-- ALTER TABLE users ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE vacancies ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE user_vacancies ENABLE ROW LEVEL SECURITY;


-- ============================================
-- ПРИМЕРЫ ЗАПРОСОВ
-- ============================================

-- Получить пользователей для рассылки вакансии категории 'design':
-- SELECT * FROM users 
-- WHERE 'design' = ANY(categories) 
-- AND is_active = TRUE 
-- AND is_subscribed = TRUE
-- AND is_banned = FALSE;

-- Получить вакансии на модерацию:
-- SELECT * FROM user_vacancies WHERE status = 'pending' ORDER BY created_at;

-- Статистика за сегодня:
-- SELECT * FROM stats WHERE date = CURRENT_DATE;

-- Проверить rate-limit (сообщения за последний час):
-- SELECT COUNT(*) FROM send_logs 
-- WHERE user_id = ? AND sent_at > NOW() - INTERVAL '1 hour';

