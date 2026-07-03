"""
Конфигурация бота для подачи вакансий.
"""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]
MODERATION_CHAT = os.getenv("MODERATION_CHAT", "")
VACANCY_BOT_USERNAME = os.getenv("VACANCY_BOT_USERNAME", "freelancee_hubot")


# ===================================
# КАТЕГОРИИ ВАКАНСИЙ
# ===================================

CATEGORIES = {
    "it": {
        "name": "💻 IT / Development",
        "emoji": "💻",
    },
    "design": {
        "name": "🎨 Design",
        "emoji": "🎨",
    },
    "marketing": {
        "name": "📈 Marketing",
        "emoji": "📈",
    },
    "copywriting": {
        "name": "✍️ Copywriting",
        "emoji": "✍️",
    },
    "video": {
        "name": "🎬 Video / Motion",
        "emoji": "🎬",
    },
    "ai_ml": {
        "name": "🤖 AI / ML",
        "emoji": "🤖",
    },
    "other": {
        "name": "📦 Other",
        "emoji": "📦",
    },
}
