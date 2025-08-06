import os
import hmac
import hashlib
import time
from typing import Optional
from fastapi import HTTPException, Request
import logging

logger = logging.getLogger(__name__)

class WebhookSecurity:
    """Класс для обеспечения безопасности webhook'ов"""
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode() if isinstance(secret_key, str) else secret_key
    
    def verify_yookassa_signature(self, payload: bytes, signature: str, timestamp: Optional[str] = None) -> bool:
        """
        Проверка HMAC SHA-256 подписи от ЮКасса
        """
        try:
            # Проверка временной метки для защиты от replay атак
            if timestamp:
                webhook_time = int(timestamp)
                current_time = int(time.time())
                # Разрешаем 5 минут на доставку webhook
                if abs(current_time - webhook_time) > 300:
                    logger.warning(f"Webhook timestamp too old: {webhook_time} vs {current_time}")
                    return False
            
            # Вычисляем HMAC подпись
            expected_signature = hmac.new(
                self.secret_key,
                payload,
                digestmod=hashlib.sha256
            ).hexdigest()
            
            # Безопасное сравнение подписей
            return hmac.compare_digest(expected_signature, signature)
            
        except Exception as e:
            logger.error(f"Signature verification error: {e}")
            return False
    
    def create_signature(self, payload: bytes) -> str:
        """Создание HMAC подписи для исходящих запросов"""
        return hmac.new(
            self.secret_key,
            payload,
            digestmod=hashlib.sha256
        ).hexdigest()

class ReplayProtection:
    """Защита от replay атак с использованием Redis"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.processed_events = set()  # Fallback для случая без Redis
    
    def is_event_processed(self, event_id: str) -> bool:
        """Проверка, был ли уже обработан данный event"""
        if self.redis_client:
            try:
                return self.redis_client.exists(f"webhook_event:{event_id}")
            except Exception as e:
                logger.error(f"Redis check error: {e}")
                # Fallback на in-memory проверку
                return event_id in self.processed_events
        else:
            return event_id in self.processed_events
    
    def mark_event_processed(self, event_id: str, ttl: int = 3600):
        """Отметить event как обработанный"""
        if self.redis_client:
            try:
                self.redis_client.setex(f"webhook_event:{event_id}", ttl, "processed")
            except Exception as e:
                logger.error(f"Redis set error: {e}")
                # Fallback на in-memory хранение
                self.processed_events.add(event_id)
        else:
            self.processed_events.add(event_id)
            # Ограничиваем размер in-memory кеша
            if len(self.processed_events) > 10000:
                # Удаляем половину старых записей
                old_events = list(self.processed_events)[:5000]
                for event in old_events:
                    self.processed_events.discard(event)

async def validate_webhook_request(request: Request, webhook_security: WebhookSecurity, replay_protection: ReplayProtection) -> dict:
    """
    Валидация входящего webhook запроса
    """
    try:
        # Получаем сырые данные
        payload = await request.body()
        
        # Извлекаем заголовки безопасности
        signature = request.headers.get("X-Yookassa-Signature")
        timestamp = request.headers.get("X-Yookassa-Timestamp")
        event_id = request.headers.get("X-Yookassa-Event-Id")
        
        if not signature:
            raise HTTPException(status_code=400, detail="Missing signature header")
        
        # Проверяем подпись
        if not webhook_security.verify_yookassa_signature(payload, signature, timestamp):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Защита от replay атак
        if event_id:
            if replay_protection.is_event_processed(event_id):
                raise HTTPException(status_code=409, detail="Event already processed")
            replay_protection.mark_event_processed(event_id)
        
        # Парсим JSON
        import json
        data = json.loads(payload.decode())
        
        return data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Webhook validation error: {e}")
        raise HTTPException(status_code=400, detail="Invalid webhook request")
