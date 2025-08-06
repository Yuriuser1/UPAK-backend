import os
import logging
import asyncio
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError
from datetime import datetime

logger = logging.getLogger(__name__)

class AsyncTelegramBot:
    """Асинхронный Telegram бот для UPAK"""
    
    def __init__(self, token: str):
        self.token = token
        self.bot = Bot(token=token)
        self._initialized = False
    
    async def initialize(self):
        """Инициализация бота"""
        try:
            # Проверяем токен
            me = await self.bot.get_me()
            logger.info(f"Telegram bot initialized: @{me.username}")
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            return False
    
    async def send_message(
        self, 
        chat_id: int, 
        text: str, 
        parse_mode: str = "HTML",
        disable_web_page_preview: bool = True
    ) -> bool:
        """
        Отправка сообщения с обработкой ошибок
        """
        if not self._initialized:
            logger.warning("Bot not initialized, attempting to initialize...")
            if not await self.initialize():
                return False
        
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            logger.info(f"Message sent to {chat_id}")
            return True
            
        except TelegramError as e:
            logger.error(f"Telegram error sending message to {chat_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending message to {chat_id}: {e}")
            return False
    
    async def send_order_created_notification(
        self, 
        chat_id: int, 
        order_id: str, 
        product_name: str,
        generated_images_count: int = 0
    ) -> bool:
        """Уведомление о создании заказа"""
        message = f"""
🎉 <b>Ваш заказ создан!</b>

📋 <b>Номер заказа:</b> {order_id}
🛍 <b>Товар:</b> {product_name}
📅 <b>Дата:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

📄 PDF с карточкой товара будет доступен после оплаты.
"""
        
        if generated_images_count > 0:
            message += f"\n🖼 Сгенерировано изображений: {generated_images_count} шт."
        
        message += "\n\n💳 Для завершения заказа перейдите к оплате."
        
        return await self.send_message(chat_id, message)
    
    async def send_payment_success_notification(
        self, 
        chat_id: int, 
        order_id: str, 
        pdf_url: str
    ) -> bool:
        """Уведомление об успешной оплате"""
        message = f"""
✅ <b>Оплата прошла успешно!</b>

📋 <b>Заказ:</b> {order_id}
📅 <b>Оплачено:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

📄 <b>Ваша карточка товара готова:</b>
<a href="{pdf_url}">Скачать PDF</a>

Спасибо за использование UPAK! 🚀
"""
        
        return await self.send_message(chat_id, message)
    
    async def send_error_notification(
        self, 
        chat_id: int, 
        order_id: str, 
        error_message: str = "Произошла ошибка при обработке заказа"
    ) -> bool:
        """Уведомление об ошибке"""
        message = f"""
❌ <b>Ошибка обработки заказа</b>

📋 <b>Заказ:</b> {order_id}
📅 <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}

⚠️ {error_message}

Пожалуйста, обратитесь в поддержку или попробуйте позже.
"""
        
        return await self.send_message(chat_id, message)
    
    async def send_admin_notification(
        self, 
        admin_chat_id: int, 
        message: str
    ) -> bool:
        """Уведомление администратора"""
        admin_message = f"""
🔔 <b>Уведомление администратора</b>

📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

{message}
"""
        
        return await self.send_message(admin_chat_id, admin_message)
    
    async def close(self):
        """Закрытие соединения с ботом"""
        try:
            await self.bot.close()
            logger.info("Telegram bot connection closed")
        except Exception as e:
            logger.error(f"Error closing Telegram bot: {e}")

# Глобальный экземпляр бота
_bot_instance: Optional[AsyncTelegramBot] = None

async def get_telegram_bot() -> Optional[AsyncTelegramBot]:
    """Получение экземпляра Telegram бота"""
    global _bot_instance
    
    if _bot_instance is None:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.error("TELEGRAM_BOT_TOKEN not found in environment variables")
            return None
        
        _bot_instance = AsyncTelegramBot(token)
        if not await _bot_instance.initialize():
            _bot_instance = None
            return None
    
    return _bot_instance

async def send_telegram_notification(
    chat_id: int, 
    notification_type: str, 
    **kwargs
) -> bool:
    """
    Универсальная функция для отправки уведомлений
    
    Args:
        chat_id: ID чата
        notification_type: Тип уведомления ('order_created', 'payment_success', 'error', 'admin')
        **kwargs: Дополнительные параметры для конкретного типа уведомления
    """
    bot = await get_telegram_bot()
    if not bot:
        logger.error("Failed to get Telegram bot instance")
        return False
    
    try:
        if notification_type == "order_created":
            return await bot.send_order_created_notification(
                chat_id=chat_id,
                order_id=kwargs.get("order_id", ""),
                product_name=kwargs.get("product_name", ""),
                generated_images_count=kwargs.get("generated_images_count", 0)
            )
        
        elif notification_type == "payment_success":
            return await bot.send_payment_success_notification(
                chat_id=chat_id,
                order_id=kwargs.get("order_id", ""),
                pdf_url=kwargs.get("pdf_url", "")
            )
        
        elif notification_type == "error":
            return await bot.send_error_notification(
                chat_id=chat_id,
                order_id=kwargs.get("order_id", ""),
                error_message=kwargs.get("error_message", "Произошла ошибка")
            )
        
        elif notification_type == "admin":
            admin_chat_id = kwargs.get("admin_chat_id") or chat_id
            return await bot.send_admin_notification(
                admin_chat_id=admin_chat_id,
                message=kwargs.get("message", "")
            )
        
        else:
            logger.error(f"Unknown notification type: {notification_type}")
            return False
    
    except Exception as e:
        logger.error(f"Error sending {notification_type} notification: {e}")
        return False

async def cleanup_telegram_bot():
    """Очистка ресурсов Telegram бота"""
    global _bot_instance
    if _bot_instance:
        await _bot_instance.close()
        _bot_instance = None
