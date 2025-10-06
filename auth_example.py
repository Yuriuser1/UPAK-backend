"""
Пример реализации аутентификации с httpOnly cookies для UPAK Backend
Этот файл содержит готовый код для интеграции в ваш проект
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Response, Cookie, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import os

# ============================================================================
# НАСТРОЙКИ
# ============================================================================

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7
IS_PRODUCTION = os.getenv("ENVIRONMENT") == "production"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ============================================================================
# МОДЕЛИ
# ============================================================================

class User(BaseModel):
    """Модель пользователя"""
    id: int
    email: str
    hashed_password: str
    subscription_type: Optional[str] = "free"
    subscription_expires: Optional[datetime] = None
    cards_limit: Optional[int] = 0
    cards_used: Optional[int] = 0

class UserInDB(User):
    """Пользователь в БД с хешированным паролем"""
    pass

class UserResponse(BaseModel):
    """Ответ с данными пользователя (без пароля)"""
    email: str
    subscription_type: Optional[str]
    subscription_expires: Optional[datetime]
    cards_limit: Optional[int]
    cards_used: Optional[int]

# ============================================================================
# ФУНКЦИИ РАБОТЫ С ПАРОЛЯМИ
# ============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Хеширование пароля"""
    return pwd_context.hash(password)

# ============================================================================
# ФУНКЦИИ РАБОТЫ С JWT
# ============================================================================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Создание JWT токена
    
    Args:
        data: Данные для кодирования в токен (обычно {"sub": email})
        expires_delta: Время жизни токена (по умолчанию 7 дней)
    
    Returns:
        Закодированный JWT токен
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# ============================================================================
# ФУНКЦИИ РАБОТЫ С БАЗОЙ ДАННЫХ (ЗАГЛУШКИ - ЗАМЕНИТЕ НА СВОЮ ЛОГИКУ)
# ============================================================================

# TODO: Замените эти функции на реальную работу с вашей БД
fake_users_db = {
    "test@upak.space": {
        "id": 1,
        "email": "test@upak.space",
        "hashed_password": get_password_hash("StrongPass123"),
        "subscription_type": "free",
        "subscription_expires": None,
        "cards_limit": 3,
        "cards_used": 0
    }
}

def get_user_by_email(email: str) -> Optional[UserInDB]:
    """
    Получение пользователя из БД по email
    
    TODO: Замените на реальный запрос к вашей БД
    """
    if email in fake_users_db:
        user_dict = fake_users_db[email]
        return UserInDB(**user_dict)
    return None

def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
    """
    Аутентификация пользователя
    
    Args:
        email: Email пользователя
        password: Пароль в открытом виде
    
    Returns:
        Объект пользователя или None если аутентификация не удалась
    """
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

# ============================================================================
# DEPENDENCY: ПОЛУЧЕНИЕ ТЕКУЩЕГО ПОЛЬЗОВАТЕЛЯ
# ============================================================================

async def get_current_user(access_token: Optional[str] = Cookie(None)) -> UserInDB:
    """
    Получение текущего пользователя из httpOnly cookie
    
    Эта функция используется как dependency в защищенных эндпоинтах:
    @app.get("/v2/me")
    async def get_me(current_user: User = Depends(get_current_user)):
        return current_user
    
    Args:
        access_token: JWT токен из httpOnly cookie
    
    Returns:
        Объект текущего пользователя
    
    Raises:
        HTTPException: Если токен отсутствует, невалиден или пользователь не найден
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not access_token:
        raise credentials_exception
    
    try:
        # Декодирование JWT токена
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    # Получение пользователя из БД
    user = get_user_by_email(email)
    if user is None:
        raise credentials_exception
    
    return user

# ============================================================================
# РОУТЕР АУТЕНТИФИКАЦИИ
# ============================================================================

router = APIRouter(prefix="/v2/auth", tags=["authentication"])

@router.post("/token")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    Вход в систему
    
    Устанавливает httpOnly cookie с JWT токеном при успешной аутентификации.
    
    Args:
        response: FastAPI Response для установки cookie
        form_data: Данные формы (username=email, password)
    
    Returns:
        Сообщение об успешном входе
    
    Raises:
        HTTPException: Если email или пароль неверны
    """
    # Аутентификация пользователя
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Создание JWT токена
    access_token_expires = timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires
    )
    
    # Установка httpOnly cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,           # Защита от XSS
        secure=IS_PRODUCTION,    # HTTPS only в продакшене
        samesite="lax",          # Защита от CSRF
        max_age=60 * 60 * 24 * ACCESS_TOKEN_EXPIRE_DAYS,  # 7 дней в секундах
        path="/"                 # Доступен для всех путей
    )
    
    return {"message": "Login successful"}

@router.post("/logout")
async def logout(response: Response):
    """
    Выход из системы
    
    Удаляет httpOnly cookie с JWT токеном.
    
    Args:
        response: FastAPI Response для удаления cookie
    
    Returns:
        Сообщение об успешном выходе
    """
    response.delete_cookie(
        key="access_token",
        path="/",
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="lax"
    )
    
    return {"message": "Logout successful"}

# ============================================================================
# ПРИМЕР ЗАЩИЩЕННЫХ ЭНДПОИНТОВ
# ============================================================================

# Создайте отдельный роутер для защищенных эндпоинтов
protected_router = APIRouter(prefix="/v2", tags=["protected"])

@protected_router.get("/me", response_model=UserResponse)
async def get_me(current_user: UserInDB = Depends(get_current_user)):
    """
    Получение информации о текущем пользователе
    
    Требует аутентификации через httpOnly cookie.
    """
    return UserResponse(
        email=current_user.email,
        subscription_type=current_user.subscription_type,
        subscription_expires=current_user.subscription_expires,
        cards_limit=current_user.cards_limit,
        cards_used=current_user.cards_used
    )

@protected_router.get("/cards")
async def get_cards(
    current_user: UserInDB = Depends(get_current_user),
    limit: int = 20,
    offset: int = 0
):
    """
    Получение карточек пользователя
    
    Требует аутентификации через httpOnly cookie.
    """
    # TODO: Реализуйте получение карточек из БД
    return []

@protected_router.get("/payments")
async def get_payments(
    current_user: UserInDB = Depends(get_current_user),
    limit: int = 20
):
    """
    Получение платежей пользователя
    
    Требует аутентификации через httpOnly cookie.
    """
    # TODO: Реализуйте получение платежей из БД
    return []

# ============================================================================
# ИНТЕГРАЦИЯ В MAIN.PY
# ============================================================================

"""
Добавьте в ваш main.py:

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import auth_example

app = FastAPI()

# CORS настройки (КРИТИЧЕСКИ ВАЖНО для работы с cookies)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",      # Для разработки
        "https://upak.space",          # Продакшен
        "https://www.upak.space"       # Продакшен с www
    ],
    allow_credentials=True,  # ⚠️ ОБЯЗАТЕЛЬНО для cookies!
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(auth_example.router)
app.include_router(auth_example.protected_router)

# Ваши остальные эндпоинты...
"""
