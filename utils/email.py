
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def send_password_reset_email(email: str, token: str, username: str) -> bool:
    """
    Отправка email с токеном для сброса пароля
    
    В production версии здесь должна быть интеграция с email сервисом
    (например, SendGrid, AWS SES, или SMTP)
    
    Для MVP версии просто логируем токен
    """
    reset_url = f"{os.getenv('FRONTEND_URL', 'https://upak.space')}/reset-password?token={token}"
    
    # TODO: Интегрировать реальный email сервис
    logger.info(f"Password reset email for {email}")
    logger.info(f"Reset URL: {reset_url}")
    logger.info(f"Token: {token}")
    
    # Временное решение для MVP - вывод в консоль
    print(f"\n{'='*60}")
    print(f"PASSWORD RESET EMAIL")
    print(f"To: {email}")
    print(f"Username: {username}")
    print(f"Reset URL: {reset_url}")
    print(f"Token: {token}")
    print(f"{'='*60}\n")
    
    return True
