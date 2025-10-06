
"""
Скрипт инициализации базы данных
Создает все необходимые таблицы
"""
import sys
import os

# Добавляем родительскую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db, engine
from models import User, PasswordResetToken

def main():
    print("Initializing database...")
    init_db()
    print("Database initialized successfully!")
    
    # Проверка созданных таблиц
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Tables created: {tables}")

if __name__ == "__main__":
    main()
