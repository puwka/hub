-- Модерация вакансий перед рассылкой пользователям
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS moderation_status VARCHAR(20) DEFAULT 'approved';
ALTER TABLE vacancies ADD COLUMN IF NOT EXISTS moderation_chat_message_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_vacancies_moderation
    ON vacancies(moderation_status, is_sent);

-- Существующие вакансии — уже одобрены
UPDATE vacancies SET moderation_status = 'approved' WHERE moderation_status IS NULL;
