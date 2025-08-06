import logging
import traceback
import json
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum
from dataclasses import dataclass, asdict
from contextlib import contextmanager

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ErrorSeverity(str, Enum):
    """Уровни серьезности ошибок"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Категории ошибок"""
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    BUSINESS_LOGIC = "business_logic"
    EXTERNAL_SERVICE = "external_service"
    DATABASE = "database"
    NETWORK = "network"
    SYSTEM = "system"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Контекст ошибки для структурированного логирования"""
    error_id: str
    timestamp: str
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    details: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[str] = None
    stack_trace: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь для логирования"""
        return {k: v for k, v in asdict(self).items() if v is not None}


class StructuredLogger:
    """Структурированный логгер для UPAK"""
    
    def __init__(self, name: str = "upak_backend"):
        self.logger = logging.getLogger(name)
        self._setup_logger()
    
    def _setup_logger(self):
        """Настройка структурированного логгера"""
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            formatter = StructuredFormatter()
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def log_error(self, error_context: ErrorContext):
        """Логирование ошибки с контекстом"""
        log_data = error_context.to_dict()
        
        if error_context.severity == ErrorSeverity.CRITICAL:
            self.logger.critical(json.dumps(log_data, ensure_ascii=False))
        elif error_context.severity == ErrorSeverity.HIGH:
            self.logger.error(json.dumps(log_data, ensure_ascii=False))
        elif error_context.severity == ErrorSeverity.MEDIUM:
            self.logger.warning(json.dumps(log_data, ensure_ascii=False))
        else:
            self.logger.info(json.dumps(log_data, ensure_ascii=False))
    
    def log_info(self, message: str, **kwargs):
        """Информационное логирование"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO",
            "message": message,
            **kwargs
        }
        self.logger.info(json.dumps(log_data, ensure_ascii=False))
    
    def log_warning(self, message: str, **kwargs):
        """Предупреждение"""
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "WARNING",
            "message": message,
            **kwargs
        }
        self.logger.warning(json.dumps(log_data, ensure_ascii=False))


class StructuredFormatter(logging.Formatter):
    """Форматтер для структурированных логов"""
    
    def format(self, record):
        # Если сообщение уже в JSON формате, возвращаем как есть
        try:
            json.loads(record.getMessage())
            return record.getMessage()
        except (json.JSONDecodeError, ValueError):
            # Иначе форматируем как структурированный лог
            log_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno
            }
            
            if record.exc_info:
                log_data["exception"] = self.formatException(record.exc_info)
            
            return json.dumps(log_data, ensure_ascii=False)


class UPAKException(Exception):
    """Базовый класс для исключений UPAK"""
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 500
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.status_code = status_code
        self.error_id = self._generate_error_id()
    
    def _generate_error_id(self) -> str:
        """Генерация уникального ID ошибки"""
        import uuid
        return f"ERR_{uuid.uuid4().hex[:8].upper()}"
    
    def to_error_context(self, request: Optional[Request] = None) -> ErrorContext:
        """Преобразование в ErrorContext"""
        return ErrorContext(
            error_id=self.error_id,
            timestamp=datetime.utcnow().isoformat(),
            severity=self.severity,
            category=self.category,
            message=self.message,
            details=self.details,
            endpoint=str(request.url.path) if request else None,
            method=request.method if request else None,
            stack_trace=traceback.format_exc()
        )


class ValidationException(UPAKException):
    """Исключение валидации данных"""
    
    def __init__(self, message: str, field: str = None, **kwargs):
        details = kwargs.get('details', {})
        if field:
            details['field'] = field
        
        super().__init__(
            message=message,
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            details=details,
            status_code=422,
            **{k: v for k, v in kwargs.items() if k != 'details'}
        )


class ExternalServiceException(UPAKException):
    """Исключение внешнего сервиса"""
    
    def __init__(self, service_name: str, message: str, **kwargs):
        details = kwargs.get('details', {})
        details['service'] = service_name
        
        super().__init__(
            message=f"{service_name}: {message}",
            category=ErrorCategory.EXTERNAL_SERVICE,
            severity=ErrorSeverity.HIGH,
            details=details,
            status_code=503,
            **{k: v for k, v in kwargs.items() if k != 'details'}
        )


class BusinessLogicException(UPAKException):
    """Исключение бизнес-логики"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.BUSINESS_LOGIC,
            severity=ErrorSeverity.MEDIUM,
            status_code=400,
            **kwargs
        )


class DatabaseException(UPAKException):
    """Исключение базы данных"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.HIGH,
            status_code=503,
            **kwargs
        )


class ErrorHandler:
    """Централизованный обработчик ошибок"""
    
    def __init__(self):
        self.logger = StructuredLogger()
        self.fallback_responses = {
            ErrorCategory.VALIDATION: "Данные не прошли валидацию",
            ErrorCategory.EXTERNAL_SERVICE: "Временно недоступен внешний сервис",
            ErrorCategory.DATABASE: "Проблемы с базой данных",
            ErrorCategory.NETWORK: "Проблемы с сетевым соединением",
            ErrorCategory.SYSTEM: "Системная ошибка",
            ErrorCategory.BUSINESS_LOGIC: "Ошибка в бизнес-логике",
            ErrorCategory.UNKNOWN: "Произошла неизвестная ошибка"
        }
    
    def handle_exception(
        self,
        exception: Exception,
        request: Optional[Request] = None,
        user_id: Optional[str] = None
    ) -> JSONResponse:
        """Обработка исключения с возвратом JSON ответа"""
        
        if isinstance(exception, UPAKException):
            error_context = exception.to_error_context(request)
        else:
            # Обработка стандартных исключений
            error_context = ErrorContext(
                error_id=f"ERR_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                timestamp=datetime.utcnow().isoformat(),
                severity=ErrorSeverity.HIGH,
                category=self._categorize_exception(exception),
                message=str(exception),
                endpoint=str(request.url.path) if request else None,
                method=request.method if request else None,
                stack_trace=traceback.format_exc()
            )
        
        if user_id:
            error_context.user_id = user_id
        
        # Логируем ошибку
        self.logger.log_error(error_context)
        
        # Возвращаем пользователю безопасный ответ
        return self._create_error_response(error_context, exception)
    
    def _categorize_exception(self, exception: Exception) -> ErrorCategory:
        """Категоризация стандартных исключений"""
        exception_name = exception.__class__.__name__
        
        if "Validation" in exception_name or "ValueError" in exception_name:
            return ErrorCategory.VALIDATION
        elif "Connection" in exception_name or "Timeout" in exception_name:
            return ErrorCategory.NETWORK
        elif "Database" in exception_name or "SQL" in exception_name:
            return ErrorCategory.DATABASE
        else:
            return ErrorCategory.UNKNOWN
    
    def _create_error_response(
        self,
        error_context: ErrorContext,
        exception: Exception
    ) -> JSONResponse:
        """Создание безопасного ответа об ошибке"""
        
        # Определяем статус код
        if isinstance(exception, UPAKException):
            status_code = exception.status_code
        elif isinstance(exception, HTTPException):
            status_code = exception.status_code
        else:
            status_code = 500
        
        # Создаем безопасный ответ
        response_data = {
            "error": True,
            "error_id": error_context.error_id,
            "message": self._get_user_friendly_message(error_context, exception),
            "timestamp": error_context.timestamp
        }
        
        # Добавляем детали только для некритичных ошибок
        if (error_context.severity in [ErrorSeverity.LOW, ErrorSeverity.MEDIUM] and 
            isinstance(exception, UPAKException)):
            response_data["details"] = exception.details
        
        return JSONResponse(
            status_code=status_code,
            content=response_data
        )
    
    def _get_user_friendly_message(
        self,
        error_context: ErrorContext,
        exception: Exception
    ) -> str:
        """Получение пользовательского сообщения об ошибке"""
        
        if isinstance(exception, UPAKException):
            return exception.message
        
        # Для критичных ошибок возвращаем общее сообщение
        if error_context.severity == ErrorSeverity.CRITICAL:
            return "Произошла критическая ошибка. Обратитесь в поддержку."
        
        return self.fallback_responses.get(
            error_context.category,
            "Произошла ошибка при обработке запроса"
        )


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware для глобальной обработки ошибок"""
    
    def __init__(self, app, error_handler: ErrorHandler = None):
        super().__init__(app)
        self.error_handler = error_handler or ErrorHandler()
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            return self.error_handler.handle_exception(exc, request)


@contextmanager
def graceful_degradation(
    fallback_value: Any = None,
    log_error: bool = True,
    error_message: str = "Operation failed, using fallback"
):
    """
    Контекстный менеджер для graceful degradation
    
    Args:
        fallback_value: Значение по умолчанию при ошибке
        log_error: Логировать ли ошибку
        error_message: Сообщение для логирования
    """
    logger = StructuredLogger()
    
    try:
        yield
    except Exception as e:
        if log_error:
            error_context = ErrorContext(
                error_id=f"GD_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                timestamp=datetime.utcnow().isoformat(),
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.SYSTEM,
                message=f"{error_message}: {str(e)}",
                stack_trace=traceback.format_exc()
            )
            logger.log_error(error_context)
        
        return fallback_value


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Декоратор для повторных попыток с экспоненциальной задержкой
    
    Args:
        max_retries: Максимальное количество попыток
        base_delay: Базовая задержка в секундах
        max_delay: Максимальная задержка в секундах
        backoff_factor: Фактор увеличения задержки
        exceptions: Типы исключений для повтора
    """
    import asyncio
    import functools
    
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = StructuredLogger()
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.log_error(ErrorContext(
                            error_id=f"RETRY_FAILED_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                            timestamp=datetime.utcnow().isoformat(),
                            severity=ErrorSeverity.HIGH,
                            category=ErrorCategory.SYSTEM,
                            message=f"Function {func.__name__} failed after {max_retries} retries",
                            details={"attempts": attempt + 1, "error": str(e)},
                            stack_trace=traceback.format_exc()
                        ))
                        raise
                    
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    logger.log_warning(
                        f"Retry attempt {attempt + 1} for {func.__name__}",
                        delay=delay,
                        error=str(e)
                    )
                    await asyncio.sleep(delay)
            
            raise last_exception
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            import time
            logger = StructuredLogger()
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.log_error(ErrorContext(
                            error_id=f"RETRY_FAILED_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                            timestamp=datetime.utcnow().isoformat(),
                            severity=ErrorSeverity.HIGH,
                            category=ErrorCategory.SYSTEM,
                            message=f"Function {func.__name__} failed after {max_retries} retries",
                            details={"attempts": attempt + 1, "error": str(e)},
                            stack_trace=traceback.format_exc()
                        ))
                        raise
                    
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    logger.log_warning(
                        f"Retry attempt {attempt + 1} for {func.__name__}",
                        delay=delay,
                        error=str(e)
                    )
                    time.sleep(delay)
            
            raise last_exception
        
        # Возвращаем соответствующий wrapper в зависимости от типа функции
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Глобальный экземпляр обработчика ошибок
global_error_handler = ErrorHandler()
