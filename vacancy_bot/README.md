# 🚀 Vacancy Bot — Telegram биржа вакансий

Telegram-бот для автоматического сбора и рассылки вакансий.

## ✨ Возможности

- 📡 **Парсинг** Telegram-каналов и групп через Telethon
- 🎯 **Категоризация** вакансий (IT, Design, Marketing и др.)
- 📬 **Автоматическая рассылка** по выбранным категориям
- 👤 **Добавление вакансий** пользователями с модерацией
- 🔐 **Админ-панель** для управления ботом
- 🛡 **Anti-flood** и rate limiting
- 🚫 **Фильтрация спама** и дубликатов

## 📋 Требования

- Python 3.11+
- Supabase аккаунт (бесплатный)
- Telegram Bot Token (@BotFather)
- Telegram API credentials (my.telegram.org)

## 🛠 Установка

### 1. Клонирование и настройка окружения

```bash
cd vacancy_bot
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Настройка Supabase

1. Создайте проект на [supabase.com](https://supabase.com)
2. Откройте SQL Editor
3. Выполните скрипт `database/schema.sql`
4. Скопируйте URL и API Key из Settings → API

### 3. Настройка переменных окружения

Скопируйте `env_example.txt` в `.env` и заполните:

```env
# Telegram Bot (получить у @BotFather)
BOT_TOKEN=123456:ABC...

# Telethon (получить на my.telegram.org)
TELETHON_API_ID=12345678
TELETHON_API_HASH=abc123...
TELETHON_PHONE=+79991234567

# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...

# Админ (ваш Telegram ID, узнать у @userinfobot)
ADMIN_IDS=123456789

# Обязательный канал для подписки
REQUIRED_CHANNEL=@your_channel
```

### 4. Первый запуск

```bash
python main.py
```

При первом запуске Telethon попросит ввести код из Telegram SMS.

## 📁 Структура проекта

```
vacancy_bot/
├── main.py              # Точка входа
├── config.py            # Конфигурация и категории
├── scheduler.py         # APScheduler задачи
│
├── database/
│   ├── __init__.py
│   ├── supabase_client.py   # Клиент Supabase
│   └── schema.sql           # SQL схема
│
├── parser/
│   ├── __init__.py
│   └── telethon_parser.py   # Парсер каналов
│
├── handlers/
│   ├── __init__.py
│   ├── user.py              # Основные команды
│   ├── categories.py        # Выбор категорий
│   ├── user_vacancy.py      # Добавление вакансий
│   └── admin.py             # Админ-панель
│
├── keyboards/
│   ├── __init__.py
│   └── main.py              # Все клавиатуры
│
├── services/
│   ├── __init__.py
│   └── distribution.py      # Рассылка вакансий
│
├── requirements.txt
└── README.md
```

## 🎮 Команды бота

### Пользователь
- `/start` — Запуск бота
- `/help` — Справка
- `/categories` — Выбор категорий
- `/stats` — Моя статистика

### Администратор
- `/admin` — Админ-панель

## 📡 Добавление источников парсинга

1. Откройте админ-панель: `/admin`
2. Нажмите "📡 Источники парсинга"
3. Нажмите "➕ Добавить источник"
4. Отправьте @username канала или группы

**Важно:** Ваш Telethon-аккаунт должен быть подписан на эти каналы/группы.

## 🔧 Настройка парсинга

В `config.py` можно настроить:

```python
CATEGORIES = {
    "it": {
        "name": "💻 IT / Development",
        "keywords": ["python", "javascript", ...],
        ...
    },
    ...
}

SPAM_KEYWORDS = [
    "казино", "ставки", ...
]
```

## 📊 База данных

### Таблицы

| Таблица | Описание |
|---------|----------|
| `users` | Пользователи бота |
| `vacancies` | Вакансии из парсинга |
| `sent_vacancies` | История отправок |
| `user_vacancies` | Вакансии от пользователей |
| `parse_sources` | Источники парсинга |
| `send_logs` | Логи для rate-limit |

## ⚡ Примеры запросов Supabase

```sql
-- Пользователи для рассылки категории 'design'
SELECT * FROM users 
WHERE 'design' = ANY(categories) 
AND is_active = TRUE 
AND is_subscribed = TRUE;

-- Вакансии на модерацию
SELECT * FROM user_vacancies 
WHERE status = 'pending' 
ORDER BY created_at;

-- Статистика по категориям
SELECT category, COUNT(*) as count 
FROM vacancies 
GROUP BY category;
```

## 🛡 Безопасность

- Session файл Telethon хранится локально
- Ключи Supabase только в .env
- Rate-limiting для защиты от спама
- Проверка подписки на канал

## 🐛 Решение проблем

### Telethon не авторизуется
Удалите файл `vacancy_parser.session` и запустите заново.

### Ошибки Supabase
Проверьте правильность URL и KEY в .env.

### Бот не видит сообщения
Убедитесь, что Telethon-аккаунт подписан на источники.

## 📄 Лицензия

MIT License

## 👨‍💻 Автор

Created with ❤️ by AI Assistant

