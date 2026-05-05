-- Скрипт для активации статуса x2
-- Выполните в Supabase SQL Editor

-- Вариант 1: Активировать x2 для конкретного пользователя по Telegram ID
-- Замените YOUR_TELEGRAM_ID на ваш Telegram ID (можно узнать у @userinfobot)
UPDATE users
SET x2_until = (NOW() AT TIME ZONE 'UTC') + INTERVAL '30 days'
WHERE tg_id = YOUR_TELEGRAM_ID;

-- Вариант 2: Активировать x2 для пользователя по username
-- Замените 'your_username' на ваш username (без @)
UPDATE users
SET x2_until = (NOW() AT TIME ZONE 'UTC') + INTERVAL '30 days'
WHERE username = 'your_username';

-- Вариант 3: Активировать x2 для всех администраторов (если у вас есть таблица админов)
-- Раскомментируйте и используйте, если нужно:
-- UPDATE users
-- SET x2_until = NOW() + INTERVAL '30 days'
-- WHERE tg_id IN (123456789, 987654321);  -- Замените на ID админов

-- Проверка результата (после выполнения UPDATE)
SELECT 
    tg_id,
    username,
    first_name,
    x2_until,
    NOW() as current_time,
    CASE 
        WHEN x2_until > (NOW() AT TIME ZONE 'UTC') THEN 'Активен'
        ELSE 'Неактивен'
    END as status,
    EXTRACT(EPOCH FROM (x2_until - (NOW() AT TIME ZONE 'UTC')))/3600 as hours_left
FROM users
WHERE tg_id = YOUR_TELEGRAM_ID;  -- Замените на ваш ID

