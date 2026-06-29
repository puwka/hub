-- Ручная активация / продление подписки на вакансии
-- Выполнить в Supabase SQL Editor

-- Вариант 1: по Telegram ID
UPDATE users
SET x2_until = GREATEST(COALESCE(x2_until, NOW()), NOW()) + INTERVAL '30 days'
WHERE tg_id = 1001949438;  -- замените на свой tg_id

-- Вариант 2: по username
-- UPDATE users
-- SET x2_until = GREATEST(COALESCE(x2_until, NOW()), NOW()) + INTERVAL '30 days'
-- WHERE username = 'your_username';

-- Проверка
SELECT
    tg_id,
    username,
    x2_until,
    CASE WHEN x2_until > NOW() THEN 'активна' ELSE 'неактивна' END AS status,
    ROUND(EXTRACT(EPOCH FROM (x2_until - NOW())) / 86400, 1) AS days_left
FROM users
WHERE tg_id = 1001949438;
