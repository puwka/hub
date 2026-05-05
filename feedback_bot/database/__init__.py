"""
Модуль для работы с базой данных Supabase.
"""

from .supabase_client import SupabaseClient

# Создаем глобальный инстанс клиента
db = SupabaseClient()

