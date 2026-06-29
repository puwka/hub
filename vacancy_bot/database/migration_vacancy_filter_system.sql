-- ============================================
-- МИГРАЦИЯ: многоступенчатая фильтрация вакансий
-- Выполнить в Supabase SQL Editor
-- ============================================

-- Расширение таблицы vacancies
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS original_text TEXT;
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS title VARCHAR(500);
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS company VARCHAR(255);
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS salary VARCHAR(255);
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS employment VARCHAR(100);
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS location VARCHAR(255);
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS stack JSONB DEFAULT '[]';
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS contacts JSONB DEFAULT '[]';
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS remote BOOLEAN DEFAULT FALSE;
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS quality_score INT DEFAULT 0;
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS simhash VARCHAR(16);
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS embedding JSONB;
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS filter_confidence INT;
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS filter_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_vacancies_simhash ON vacancies(simhash);
CREATE INDEX IF NOT EXISTS idx_vacancies_quality ON vacancies(quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_vacancies_created ON vacancies(created_at DESC);

-- Логи фильтрации
CREATE TABLE IF NOT EXISTS parse_filter_logs (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT,
    chat_id VARCHAR(255),
    source VARCHAR(255),
    decision VARCHAR(20) NOT NULL,
    stage VARCHAR(50),
    reason TEXT,
    confidence INT,
    category VARCHAR(50),
    quality_score INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parse_filter_logs_created ON parse_filter_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_parse_filter_logs_source ON parse_filter_logs(source);
CREATE INDEX IF NOT EXISTS idx_parse_filter_logs_decision ON parse_filter_logs(decision);

-- Дневные метрики парсинга
CREATE TABLE IF NOT EXISTS parse_metrics (
    id BIGSERIAL PRIMARY KEY,
    date DATE UNIQUE NOT NULL DEFAULT CURRENT_DATE,
    messages_received INT DEFAULT 0,
    vacancies_saved INT DEFAULT 0,
    vacancies_rejected INT DEFAULT 0,
    duplicates_rejected INT DEFAULT 0,
    avg_quality_score FLOAT DEFAULT 0,
    quality_score_sum INT DEFAULT 0,
    quality_score_count INT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Качество источников
CREATE TABLE IF NOT EXISTS parse_source_quality (
    source_id VARCHAR(255) PRIMARY KEY,
    messages_total INT DEFAULT 0,
    saved_total INT DEFAULT 0,
    rejected_total INT DEFAULT 0,
    duplicates_total INT DEFAULT 0,
    quality_score_sum INT DEFAULT 0,
    quality_score_count INT DEFAULT 0,
    avg_quality_score FLOAT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS отключен по умолчанию (как в основной схеме)
