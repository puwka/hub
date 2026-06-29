"""
Конфигурация приложения.
Загружает настройки из .env файла.
"""

import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()


@dataclass
class BotConfig:
    """Настройки Telegram бота"""
    token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    

@dataclass
class TelethonConfig:
    """Настройки Telethon (парсинг через user account)"""
    api_id: int = field(default_factory=lambda: int(os.getenv("TELETHON_API_ID", "0")))
    api_hash: str = field(default_factory=lambda: os.getenv("TELETHON_API_HASH", ""))
    phone: str = field(default_factory=lambda: os.getenv("TELETHON_PHONE", ""))
    session_name: str = "vacancy_parser"


@dataclass
class SupabaseConfig:
    """Настройки Supabase"""
    url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    key: str = field(default_factory=lambda: os.getenv("SUPABASE_KEY", ""))


@dataclass
class AdminConfig:
    """Настройки администратора"""
    ids: List[int] = field(default_factory=lambda: [
        int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") 
        if x.strip().isdigit()
    ])


@dataclass
class ChannelConfig:
    """Настройки каналов"""
    required_channel: str = field(default_factory=lambda: os.getenv("REQUIRED_CHANNEL", ""))
    add_vacancy_bot: str = field(default_factory=lambda: os.getenv("ADD_VACANCY_BOT", ""))
    feedback_bot: str = field(default_factory=lambda: os.getenv("FEEDBACK_BOT", ""))
    reviews_channel: str = field(default_factory=lambda: os.getenv("REVIEWS_CHANNEL", ""))
    moderation_chat: str = field(default_factory=lambda: os.getenv("MODERATION_CHAT", "").strip())


def get_moderation_chat_id() -> str | int | None:
    """ID или @username чата модерации вакансий."""
    chat = config.channel.moderation_chat
    if not chat:
        return None
    stripped = chat.strip()
    if stripped.lstrip("-").isdigit():
        return int(stripped)
    return stripped if stripped.startswith("@") else f"@{stripped}"


def moderation_enabled() -> bool:
    return bool(config.channel.moderation_chat)


# ============================================
# КОНСТАНТЫ
# ============================================

# Максимальная длина текста вакансии (символов)
MAX_VACANCY_LENGTH = 500

# Бонус за каждого приглашённого друга (дней подписки)
REFERRAL_BONUS_DAYS = 1

# Подписка при первом входе в бота
WELCOME_SUBSCRIPTION_DAYS = 5

# Бонус за одобренный отзыв
REVIEW_BONUS_DAYS = 3

# Тарифы подписки (оплата вручную / Stars)
SUBSCRIPTION_PLANS = {
    "week": {"days": 7, "price_rub": 49, "price_stars": 50, "label": "1 неделя"},
    "month": {"days": 30, "price_rub": 199, "price_stars": 175, "label": "1 месяц"},
    "half_year": {"days": 180, "price_rub": 899, "price_stars": 750, "label": "6 месяцев"},
    "year": {"days": 365, "price_rub": 1599, "price_stars": 1300, "label": "1 год"},
}


@dataclass
class ParserConfig:
    """Настройки парсера"""
    interval_minutes: int = field(default_factory=lambda: int(os.getenv("PARSE_INTERVAL_MINUTES", "5")))
    max_vacancies_per_parse: int = field(default_factory=lambda: int(os.getenv("MAX_VACANCIES_PER_PARSE", "50")))


@dataclass
class RateLimitConfig:
    """Настройки rate limit"""
    min_delay_seconds: int = field(default_factory=lambda: int(os.getenv("MIN_DELAY_BETWEEN_MESSAGES", "2")))
    max_messages_per_hour: int = field(default_factory=lambda: int(os.getenv("MAX_MESSAGES_PER_HOUR", "30")))


@dataclass
class PaymentConfig:
    """Контакт для оплаты подписки (username или ссылка t.me)"""
    contact: str = field(default_factory=lambda: os.getenv("PAYMENT_CONTACT", "").strip())
    stars_enabled: bool = field(default_factory=lambda: os.getenv("STARS_PAYMENT_ENABLED", "true").lower() == "true")


@dataclass
class NetworkConfig:
    """Сеть: прокси для Telegram API (нужно в РФ)"""
    proxy_url: str = field(default_factory=lambda: os.getenv("PROXY_URL", "").strip())
    telegram_api_server: str = field(default_factory=lambda: os.getenv("TELEGRAM_API_SERVER", "").strip())


@dataclass
class FilterConfig:
    """Настройки многоступенчатой фильтрации"""
    min_text_length: int = field(default_factory=lambda: int(os.getenv("FILTER_MIN_TEXT_LENGTH", "150")))
    max_links: int = field(default_factory=lambda: int(os.getenv("FILTER_MAX_LINKS", "5")))
    min_llm_confidence: int = field(default_factory=lambda: int(os.getenv("FILTER_MIN_LLM_CONFIDENCE", "60")))
    min_rule_confidence: int = field(default_factory=lambda: int(os.getenv("FILTER_MIN_RULE_CONFIDENCE", "50")))
    min_quality_score: int = field(default_factory=lambda: int(os.getenv("FILTER_MIN_QUALITY_SCORE", "20")))
    simhash_similarity_threshold: float = field(
        default_factory=lambda: float(os.getenv("FILTER_SIMHASH_THRESHOLD", "0.90"))
    )
    embedding_similarity_threshold: float = field(
        default_factory=lambda: float(os.getenv("FILTER_EMBEDDING_THRESHOLD", "0.90"))
    )
    dedup_lookback_days: int = field(default_factory=lambda: int(os.getenv("FILTER_DEDUP_DAYS", "14")))
    dedup_lookback_count: int = field(default_factory=lambda: int(os.getenv("FILTER_DEDUP_COUNT", "500")))


@dataclass
class LLMConfig:
    """Настройки LLM для классификации вакансий"""
    enabled: bool = field(default_factory=lambda: os.getenv("LLM_ENABLED", "false").lower() == "true")
    api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", "").strip())
    base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip())
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini").strip())
    embedding_model: str = field(default_factory=lambda: os.getenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small").strip())
    extract_enabled: bool = field(default_factory=lambda: os.getenv("LLM_EXTRACT_ENABLED", "true").lower() == "true")
    timeout_seconds: int = field(default_factory=lambda: int(os.getenv("LLM_TIMEOUT_SECONDS", "30")))


@dataclass
class Config:
    """Главный конфиг приложения"""
    bot: BotConfig = field(default_factory=BotConfig)
    telethon: TelethonConfig = field(default_factory=TelethonConfig)
    supabase: SupabaseConfig = field(default_factory=SupabaseConfig)
    admin: AdminConfig = field(default_factory=AdminConfig)
    channel: ChannelConfig = field(default_factory=ChannelConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    payment: PaymentConfig = field(default_factory=PaymentConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


# Глобальный инстанс конфига
config = Config()


# ===================================
# КАТЕГОРИИ ВАКАНСИЙ
# ===================================

CATEGORIES = {
    "it": {
        "name": "💻 IT / Development",
        "keywords": [
            "python", "javascript", "java", "react", "node", "frontend", 
            "backend", "fullstack", "devops", "developer", "программист",
            "разработчик", "веб-разработка", "мобильная разработка", "ios",
            "android", "flutter", "django", "fastapi", "php", "laravel",
            "vue", "angular", "typescript", "golang", "rust", "c++", "c#",
            ".net", "sql", "postgresql", "mongodb", "redis", "docker",
            "kubernetes", "aws", "azure", "git", "api", "rest", "graphql"
        ],
        "emoji": "💻",
        "hashtag": "#it #development"
    },
    "design": {
        "name": "🎨 Design",
        "keywords": [
            "дизайн", "дизайнер", "ui", "ux", "figma", "photoshop", 
            "illustrator", "графический дизайн", "веб-дизайн", "логотип",
            "брендинг", "айдентика", "баннер", "креатив", "3d", "blender",
            "cinema4d", "motion", "анимация", "презентация", "инфографика"
        ],
        "emoji": "🎨",
        "hashtag": "#design #дизайн"
    },
    "marketing": {
        "name": "📈 Marketing",
        "keywords": [
            "маркетинг", "smm", "таргет", "реклама", "продвижение",
            "контекст", "seo", "контент", "стратегия", "аналитика",
            "email", "рассылка", "воронка", "лиды", "трафик", "ppc",
            "google ads", "facebook ads", "instagram", "tiktok", "youtube"
        ],
        "emoji": "📈",
        "hashtag": "#marketing #маркетинг"
    },
    "copywriting": {
        "name": "✍️ Copywriting",
        "keywords": [
            "копирайтинг", "копирайтер", "текст", "статья", "контент",
            "рерайт", "seo-текст", "продающий текст", "лендинг", "писатель",
            "редактор", "корректор", "блог", "пост", "сценарий", "нейминг"
        ],
        "emoji": "✍️",
        "hashtag": "#copywriting #копирайтинг"
    },
    "video": {
        "name": "🎬 Video / Motion",
        "keywords": [
            "видео", "монтаж", "монтажер", "монтажёр", "монтажист", "видеомонтаж",
            "видеограф", "видеограф", "оператор", "видеооператор",
            "premiere", "premiere pro", "adobe premiere",
            "after effects", "ae", "after effects",
            "davinci", "davinci resolve", "resolve",
            "motion design", "моушн дизайн", "моушн", "motion graphics",
            "анимация", "видеоанимация", "видео анимация",
            "ролик", "видеоролик", "рекламный ролик", "промо ролик",
            "youtube", "reels", "reels maker", "рилс", "рилсмейкер", 
            "рилс мейкер", "reelsmaker", "shorts", "tiktok", "тикток",
            "стриминг", "стрим", "obs", "open broadcaster",
            "цветокоррекция", "цветокор", "колорградинг",
            "композитинг", "композитинг", "vfx", "визуальные эффекты",
            "кадрирование", "кадрировка", "обрезка видео",
            "титры", "субтитры", "графика для видео",
            "видео редактор", "видеоредактор", "редактор видео"
        ],
        "emoji": "🎬",
        "hashtag": "#video #motion"
    },
    "ai_ml": {
        "name": "🤖 AI / ML",
        "keywords": [
            "ai", "ml", "machine learning", "deep learning", "нейросеть",
            "искусственный интеллект", "data science", "data analyst",
            "tensorflow", "pytorch", "nlp", "computer vision", "chatgpt",
            "gpt", "llm", "prompt", "midjourney", "stable diffusion",
            "обучение моделей", "датасет", "pandas", "numpy", "jupyter"
        ],
        "emoji": "🤖",
        "hashtag": "#ai #ml"
    },
    "other": {
        "name": "📦 Other",
        "keywords": [],  # Всё остальное
        "emoji": "📦",
        "hashtag": "#freelance #вакансия"
    }
}


# ===================================
# ФИЛЬТР СПАМА/РЕКЛАМЫ
# ===================================

SPAM_KEYWORDS = [
    # Финансовые пирамиды и мошенничество
    "казино", "ставки", "букмекер", "forex", "криптовалюта заработок",
    "пассивный доход", "без вложений", "легкие деньги", "mlm", "пирамида",
    "схема заработка", "100% гарантия", "не упусти шанс", "только сегодня",
    "срочно нужны люди", "работа на дому без опыта",
    
    # Реклама услуг
    "реклама услуг", "продвижение канала", "накрутка", "боты для",
    "купить подписчиков", "раскрутка", "реклама в канале",
    
    # Объявления о продаже/покупке
    "продам", "куплю", "продажа", "покупка", "скидка", "акция",
    "распродажа", "специальное предложение",
    
    # Образовательные курсы (не вакансии)
    "курс", "обучение", "школа", "мастер-класс", "вебинар",
    "записаться на курс", "набор на курс",
    
    # Новости и статьи
    "читайте также", "подробнее по ссылке", "источник",
    
    # Мемы и развлечения
    "мем", "прикол", "смешно", "юмор",
    
    # Общие рекламные фразы
    "переходи по ссылке", "жми на ссылку", "подписывайся",
    "лайкни", "репост", "поделись",
    
    # Сомнительные предложения
    "быстрый заработок", "заработок за час", "деньги сразу",
    "без регистрации", "без смс"
]


# ===================================
# ФИЛЬТРАЦИЯ РЕЗЮМЕ И ПРЕДЛОЖЕНИЙ УСЛУГ
# ===================================

# Сильные индикаторы резюме (если есть хотя бы один - это резюме)
RESUME_STRONG_INDICATORS = [
    # Прямые упоминания резюме
    r"\bрезюме\b",
    r"\bresume\b",
    r"\bcv\b",
    r"\bcurriculum\s+vitae\b",
    
    # Поиск работы от первого лица
    r"ищу\s+работу\b",
    r"ищу\s+заказ\b",
    r"ищу\s+проект\b",
    
    # Предложение услуг от первого лица
    r"меня\s+зовут\b",
    r"меня\s+звать\b",
    r"специализируюсь\b",
    r"специализируюсь\s+на\b",
    r"я\s+специалист\b",
    r"я\s+занимаюсь\b",
    r"готов\s+взять\b",
    r"готов\s+выполнить\b",
    r"готов\s+сделать\b",
    r"предлагаю\s+услуги\b",
    r"предлагаю\s+услугу\b",
    r"оказываю\s+услуги\b",
    r"выполню\s+работу\b",
    r"сделаю\s+работу\b",
    r"мой\s+опыт\b",
    r"у\s+меня\s+опыт\b",
    r"стоимость\s+работы\b",
    r"цена\s+за\s+работу\b",
    r"за\s+работу\b.*рубл",
    r"всего\s+\d+\s+рубл",
    r"портфолио\s+можно\b",
    r"портфолио\s+в\b",
    r"ищу\s+заказчика\b",
    r"ищу\s+клиента\b",
    r"ищу\s+сотрудничество\b",
    r"ищу\s+работодател",
    r"ищу\s+компанию\b",
    r"ищу\s+удаленную\s+работу\b",
    r"ищу\s+удаленку\b",
    r"ищу\s+фриланс\b",
    r"ищу\s+вакансию\b",
    r"ищу\s+позицию\b",
    
    # Описание опыта от первого лица
    r"мой\s+опыт\s+работы",
    r"мой\s+стаж",
    r"опыт\s+работы\s+\d+",
    r"работал\s+в",
    r"работала\s+в",
    r"имею\s+опыт",
    r"имею\s+стаж",
    
    # Контакты от первого лица
    r"обращайтесь\s+ко\s+мне",
    r"свяжитесь\s+со\s+мной",
    r"мой\s+портфолио",
    r"портфолио\s+прилагаю",
    
    # Готовность к работе (от исполнителя)
    r"готов\s+к\s+работе",
    r"готов\s+к\s+сотрудничеству",
    r"открыт\s+к\s+предложениям",
    r"открыта\s+к\s+предложениям",
    
    # Предложения услуг
    r"\bпомогу\b",
    r"готов\s+взять",
    r"возьмусь",
    r"предлагаю\s+услуги",
    r"беру\s+заказы",
    r"принимаю\s+заказы",
    
    # Английские фразы резюме
    r"\bopen\s+to\s+work\b",
    r"\bavailable\b.*\bfor\b",
    r"\bfreelancer\b",
    r"\bself.?employed\b",
    r"\bсамозанятый\b",
    r"\bсамозанятая\b",
]

# Слабые индикаторы резюме (нужно >= 2 для определения как резюме)
RESUME_WEAK_INDICATORS = [
    r"готов\s+выполнить",
    r"выполню",
    r"сделаю",
    r"мой\s+опыт",
    r"опыт\s+работы",
    r"обращайтесь",
    r"свяжитесь",
    r"портфолио",
    r"portfolio",
    r"готов\s+к\s+сотрудничеству",
    r"предлагаю\s+помощь",
    r"выполню\s+заказ",
    r"выполню\s+проект",
    r"доступен\s+для",
    r"доступна\s+для",
]

# Паттерны начала сообщения, которые указывают на резюме
RESUME_START_PATTERNS = [
    r"^ищу\s+",  # Начинается с "ищу" (но не "ищу дизайнера" - это вакансия)
    r"^предлагаю\s+",  # Начинается с "предлагаю"
    r"^готов\s+",  # Начинается с "готов"
    r"^меня\s+зовут",  # Начинается с "меня зовут"
    r"^я\s+",  # Начинается с "я" (но может быть вакансия "я ищу...")
]

# ===================================
# ФИЛЬТРАЦИЯ ВАКАНСИЙ
# ===================================

# Сильные индикаторы вакансии (приоритетные)
VACANCY_STRONG_INDICATORS = [
    r"\bищем\b",  # "ищем дизайнера"
    r"\bищу\b",  # "ищу дизайнера" (в начале сообщения или с #ищу)
    r"#ищу\b",  # Хештег #ищу
    r"\bнужен\b",  # "нужен дизайнер"
    r"\bнужна\b",  # "нужна помощь"
    r"\bтребуется\b",  # "требуется разработчик"
    r"\bтребуются\b",  # "требуются специалисты"
    r"\bнужны\b",  # "нужны дизайнеры"
    r"\bнанимаем\b",  # "нанимаем"
    r"\bhire\b",  # "hire"
    r"\blooking\s+for\b",  # "looking for"
    r"\bneed\b.*\bfor\b",  # "need ... for"
    r"\brequired\b",  # "required"
    r"\bв\s+команду\b",  # "в команду"
    r"\bвакансия\b",  # "вакансия"
    r"\bvacancy\b",  # "vacancy"
    r"\bjob\b",  # "job"
]

# Индикаторы условий работы (вакансия)
VACANCY_CONDITIONS_INDICATORS = [
    r"\bоплата\b",  # "оплата"
    r"\bзарплата\b",  # "зарплата"
    r"\bставка\b",  # "ставка"
    r"\bоклад\b",  # "оклад"
    r"\bгонорар\b",  # "гонорар"
    r"\bбюджет\b",  # "бюджет"
    r"\$\d+",  # "$1000"
    r"\d+\s*(руб|₽|usd|usdt|рублей|долларов|₴|eur|€)",  # "50000 руб"
    r"\bудаленн",  # "удаленно"
    r"\bудалённ",  # "удалённо"
    r"\bremote\b",  # "remote"
    r"\bfull.?time\b",  # "fulltime" / "full-time"
    r"\bpart.?time\b",  # "parttime" / "part-time"
    r"\bграфик\b",  # "график"
    r"\bрежим\s+работы\b",  # "режим работы"
    r"\bчасов?\b",  # "часов" / "часа"
]

# Индикаторы задач и требований (вакансия)
VACANCY_TASK_INDICATORS = [
    r"\bтребовани[яе]\b",  # "требования"
    r"\bнавык[и]\b",  # "навыки"
    r"\bумени[яе]\b",  # "умения"
    r"\bопыт\b",  # "опыт" (в контексте требований)
    r"\bвыполнить\b",  # "выполнить"
    r"\bсделать\b",  # "сделать"
    r"\bразработать\b",  # "разработать"
    r"\bсоздать\b",  # "создать"
    r"\bзадача\b",  # "задача"
    r"\bпроект\b",  # "проект"
    r"\bзаказ\b",  # "заказ"
]

# Индикаторы призыва к действию (вакансия)
VACANCY_ACTION_INDICATORS = [
    r"\bоткликн",  # "откликнись"
    r"\bотправь\b",  # "отправь"
    r"\bнаписать\b",  # "написать"
    r"\bнапиши\b",  # "напиши"
    r"\bсвяжитесь\b",  # "свяжитесь"
    r"\bнапишите\b",  # "напишите"
    r"\bпозиция\b",  # "позиция"
    r"\bработа\b",  # "работа"
]


# ===================================
# ФИЛЬТРАЦИЯ НИЗКОКАЧЕСТВЕННЫХ ВАКАНСИЙ
# ===================================

# Стоп-фразы, которые указывают на низкокачественные/сомнительные вакансии
# Если найдена хотя бы одна - вакансия отклоняется
SUSPICIOUS_VACANCY_PHRASES = [
    # Без опыта / не требуется опыт
    r"без\s+опыта",
    r"опыт\s+не\s+обязателен",
    r"опыт\s+не\s+нужен",
    r"опыт\s+не\s+требуется",
    r"без\s+навыков",
    r"навыки\s+не\s+нужны",
    
    # Работа с телефона
    r"задания\s+с\s+телефона",
    r"работа\s+с\s+телефона",
    r"работа\s+на\s+телефоне",
    r"с\s+телефона",
    r"на\s+телефоне",
    r"мобильный\s+заработок",
    
    # Опросы и отзывы
    r"пройти\s+опрос",
    r"написать\s+отзыв",
    r"оставить\s+отзыв",
    r"заполнить\s+опрос",
    r"опрос\s+за\s+деньги",
    r"отзывы\s+за\s+деньги",
    
    # Установка приложений
    r"скачать\s+приложение",
    r"установить\s+приложение",
    r"установка\s+приложений",
    r"скачивание\s+приложений",
    r"за\s+установку",
    
    # Заработок "от N в день"
    r"заработок\s+от\s+\d+",
    r"доход\s+от\s+\d+",
    r"\d+\s*₽\s+в\s+день",
    r"\d+\s*руб\s+в\s+день",
    r"\d+\s*рублей\s+в\s+день",
    r"в\s+день\s+\d+",
    r"от\s+\d+\s+₽\s+в\s+день",
    r"от\s+\d+\s+руб\s+в\s+день",
    
    # Свободный график (часто используется в низкокачественных вакансиях)
    r"свободный\s+график",
    r"свой\s+график",
    r"график\s+свободный",
    
    # Возрастные ограничения (часто в массовом наборе)
    r"от\s+18\s+лет",
    r"от\s+18\s+и\s+старше",
    r"возраст\s+от\s+18",
    
    # Гражданство (часто в массовом наборе)
    r"гражданство\s+рф",
    r"гражданство\s+россии",
    r"только\s+рф",
    r"только\s+россия",
    
    # Контакты через ЛС (подозрительно)
    r"пишите\s+в\s+лс",
    r"напишите\s+в\s+лс",
    r"в\s+личные\s+сообщения",
    r"в\s+лс\s+для\s+деталей",
    r"детали\s+в\s+лс",
    r"в\s+пм",
    r"в\s+личку",
    
    # Боты для заработка
    r"бот\s+для\s+заработка",
    r"бот\s+заработок",
    r"заработок\s+через\s+бота",
    r"телеграм\s+бот\s+заработок",
    
    # Массовый набор
    r"массовый\s+набор",
    r"набор\s+в\s+команду",
    r"набираем\s+всех",
    r"нужны\s+все",
    r"приглашаем\s+всех",
]

# Паттерны для определения отсутствия важных элементов вакансии
MISSING_COMPANY_PATTERNS = [
    r"компани[яи]",
    r"работодател",
    r"студи[яи]",
    r"агентств[оа]",
    r"бренд",
    r"проект\s+[а-я]+",  # "проект [название]"
]

MISSING_POSITION_PATTERNS = [
    r"должность",
    r"позиция",
    r"специалист",
    r"разработчик",
    r"дизайнер",
    r"менеджер",
    r"копирайтер",
    r"маркетолог",
]

# Паттерны для определения профессиональных задач
PROFESSIONAL_TASK_PATTERNS = [
    r"разработк",
    r"создан",
    r"настро",
    r"оптимиз",
    r"дизайн",
    r"верстк",
    r"программир",
    r"код",
    r"алгоритм",
    r"база\s+данных",
    r"api",
    r"интеграц",
    r"тестирован",
    r"деплой",
]

# Паттерны для определения стека/навыков
SKILLS_PATTERNS = [
    r"python|javascript|java|react|vue|angular",
    r"php|laravel|django|fastapi",
    r"figma|photoshop|illustrator",
    r"html|css|js",
    r"sql|postgresql|mongodb",
    r"git|docker|kubernetes",
    r"опыт\s+работы\s+с",
    r"знание\s+",
    r"навыки\s+работы",
]

# Паттерны для формата работы
WORK_FORMAT_PATTERNS = [
    r"удаленн",
    r"remote",
    r"full.?time",
    r"part.?time",
    r"офис",
    r"гибрид",
    r"проект",
    r"фриланс",
]

# Паттерны для описания задач (внятное описание)
TASK_DESCRIPTION_PATTERNS = [
    r"задач[аи]",
    r"обязанност",
    r"функционал",
    r"проект\s+включает",
    r"нужно\s+сделать",
    r"требуется\s+выполнить",
    r"необходимо\s+разработать",
]

# Паттерны для определения Telegram-бота (не человека)
BOT_CONTACT_PATTERNS = [
    r"@\w+bot\b",
    r"бот\s+@",
    r"через\s+бота",
    r"напишите\s+боту",
    r"бот\s+ответит",
]

# Паттерны массового набора (шаблоны)
MASS_RECRUITMENT_PATTERNS = [
    r"нужны\s+все",
    r"приглашаем\s+всех",
    r"набираем\s+всех",
    r"работа\s+для\s+всех",
    r"без\s+ограничений",
    r"без\s+требований",
    r"любой\s+опыт",
    r"любой\s+возраст",
]


# ===================================
# МНОГОСТУПЕНЧАТАЯ ФИЛЬТРАЦИЯ
# ===================================

NOT_VACANCY_PHRASES = [
    "ищу работу",
    "ищу проект",
    "мое резюме",
    "моё резюме",
    "ищу команду",
    "кто ищет разработчика",
    "посоветуйте специалиста",
    "посоветуйте фрилансера",
    "есть ли тут",
    "кто может помочь",
    "ищу заказчика",
    "ищу клиента",
    "ищу партнера",
    "ищу партнёра",
    "резюме",
    "cv",
    "curriculum vitae",
    "мой опыт",
    "обо мне",
    "готов выполнить",
    "предлагаю услуги",
    r"regex:^ищу\s+(работу|проект|команду|заказчика|клиента|удаленку|фриланс)",
    r"regex:^(предлагаю|готов)\s+",
    r"regex:посоветуйте\s+(специалист|фриланс|разработчик|дизайнер)",
]

WHITELIST_KEYWORDS = [
    "Python", "Backend", "Frontend", "React", "Vue", "Flutter",
    "AI", "ML", "LLM", "GPT", "DevOps", "QA", "Data",
    "JavaScript", "TypeScript", "Node", "Django", "FastAPI",
    "PostgreSQL", "Docker", "Kubernetes", "iOS", "Android",
]

BLACKLIST_KEYWORDS = [
    "казино", "беттинг", "букмекер", "ставки", "гемблинг",
    "криптоскам", "крипто заработок", "mlm", "пирамида",
    "арбитраж трафика", "onlyfans", "only fans",
    "forex", "бинарные опции", "хайп", "инвестиции без риска",
    "пассивный доход без", "легкие деньги", "заработок без усилий",
]


def get_payment_contact_url() -> str:
    """Ссылка t.me для оплаты подписки."""
    contact = config.payment.contact.strip()
    if not contact:
        return ""
    if contact.startswith("http"):
        return contact
    username = contact.lstrip("@")
    return f"https://t.me/{username}"


def get_payment_contact_display() -> str:
    """Отображаемый контакт (@username)."""
    contact = config.payment.contact.strip()
    if not contact:
        return "администратору бота"
    if contact.startswith("http"):
        return contact
    return contact if contact.startswith("@") else f"@{contact}"


def is_admin(user_id: int) -> bool:
    """Проверка является ли пользователь администратором"""
    return user_id in config.admin.ids


