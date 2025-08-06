from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List
from enum import Enum
import re

class PlatformType(str, Enum):
    """Поддерживаемые платформы"""
    WILDBERRIES = "wildberries"
    OZON = "ozon"
    YANDEX_MARKET = "yandex_market"

class OrderStatus(str, Enum):
    """Статусы заказа"""
    WAITING = "waiting"
    PAID = "paid"
    COMPLETED = "completed"
    FAILED = "failed"

class CreatePaymentRequest(BaseModel):
    """Модель запроса создания платежа"""
    order_id: str = Field(..., min_length=1, max_length=50, regex=r'^[A-Za-z0-9_-]+$')
    amount: float = Field(..., gt=0, le=100000, description="Сумма в рублях")
    description: str = Field(..., min_length=1, max_length=500)
    telegram_id: Optional[str] = Field(None, regex=r'^\d+$')
    
    @validator('description')
    def validate_description_security(cls, v):
        """Проверка описания на потенциально опасные строки"""
        dangerous_patterns = [
            'script', 'javascript:', 'onload', 'onerror',
            'delete from', 'drop table', 'union select',
            '<script', '</script>'
        ]
        v_lower = v.lower()
        for pattern in dangerous_patterns:
            if pattern in v_lower:
                raise ValueError(f"Description contains forbidden content: {pattern}")
        return v

class CreatePaymentResponse(BaseModel):
    """Модель ответа создания платежа"""
    payment_id: str
    confirmation_url: str
    order_id: str
    status: str = "created"

class OrderRequest(BaseModel):
    """Модель запроса создания заказа"""
    product_name: str = Field(..., min_length=2, max_length=200)
    product_features: str = Field(..., min_length=10, max_length=2000)
    platform: PlatformType
    image_data: Optional[str] = Field(None, description="Base64 encoded image")
    payment_id: Optional[str] = Field(None, regex=r'^[a-zA-Z0-9_-]+$')
    telegram_user_id: Optional[int] = Field(None, gt=0)
    
    @validator('product_name')
    def validate_product_name(cls, v):
        """Валидация названия продукта"""
        if not re.match(r'^[a-zA-Zа-яА-Я0-9\s\-_.,()]+$', v):
            raise ValueError("Product name contains invalid characters")
        return v.strip()
    
    @validator('product_features')
    def validate_product_features(cls, v):
        """Валидация характеристик продукта"""
        # Проверка на потенциально опасные строки
        dangerous_patterns = [
            'script', 'javascript:', 'onload', 'onerror',
            'delete from', 'drop table', 'union select'
        ]
        v_lower = v.lower()
        for pattern in dangerous_patterns:
            if pattern in v_lower:
                raise ValueError(f"Product features contain forbidden content: {pattern}")
        return v.strip()
    
    @validator('image_data')
    def validate_image_data(cls, v):
        """Валидация base64 изображения"""
        if v is None:
            return v
        
        # Проверяем, что это валидный base64
        import base64
        try:
            decoded = base64.b64decode(v)
            # Проверяем размер (максимум 10MB)
            if len(decoded) > 10 * 1024 * 1024:
                raise ValueError("Image too large (max 10MB)")
            
            # Проверяем, что это действительно изображение
            from PIL import Image
            import io
            Image.open(io.BytesIO(decoded))
            
        except Exception:
            raise ValueError("Invalid image data")
        
        return v

class OrderResponse(BaseModel):
    """Модель ответа создания заказа"""
    order_id: str
    pdf_url: Optional[str]
    user_image_url: Optional[str]
    generated_image_urls: List[str]
    status: OrderStatus
    message: str = "Order created successfully"

class WebhookEventData(BaseModel):
    """Модель данных webhook события"""
    event: str = Field(..., regex=r'^[a-zA-Z._]+$')
    object: dict
    
    @validator('event')
    def validate_event_type(cls, v):
        """Валидация типа события"""
        allowed_events = [
            'payment.succeeded',
            'payment.canceled',
            'payment.waiting_for_capture'
        ]
        if v not in allowed_events:
            raise ValueError(f"Unknown event type: {v}")
        return v

class HealthCheckResponse(BaseModel):
    """Модель ответа проверки здоровья"""
    status: str = "healthy"
    timestamp: str
    version: str = "1.0.0"
    services: dict
