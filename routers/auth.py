
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from database import get_db
from models import User, PasswordResetToken
from schemas import (
    UserRegister,
    UserLogin,
    UserResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    MessageResponse
)
from utils import (
    hash_password,
    verify_password,
    create_access_token,
    generate_reset_token,
    set_auth_cookie,
    clear_auth_cookie,
    get_current_user
)
from utils.email import send_password_reset_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/auth", tags=["Authentication V2"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """Регистрация нового пользователя"""
    
    # Проверка существования email
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Проверка существования username
    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Создание нового пользователя
    new_user = User(
        email=user_data.email,
        username=user_data.username,
        hashed_password=hash_password(user_data.password)
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    logger.info(f"New user registered: {new_user.email}")
    
    return new_user

@router.post("/login", response_model=MessageResponse)
async def login(
    user_data: UserLogin,
    response: Response,
    db: Session = Depends(get_db)
):
    """Вход пользователя с установкой httpOnly cookie"""
    
    # Поиск пользователя
    user = db.query(User).filter(User.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Создание токена
    access_token = create_access_token(data={"sub": user.id})
    
    # Установка cookie
    set_auth_cookie(response, access_token)
    
    logger.info(f"User logged in: {user.email}")
    
    return {"message": "Successfully logged in"}

@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    """Выход пользователя с удалением cookie"""
    clear_auth_cookie(response)
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Получение информации о текущем пользователе"""
    return current_user

@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Смена пароля для авторизованного пользователя"""
    
    # Проверка старого пароля
    if not verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )
    
    # Проверка, что новый пароль отличается от старого
    if password_data.old_password == password_data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from old password"
        )
    
    # Обновление пароля
    current_user.hashed_password = hash_password(password_data.new_password)
    db.commit()
    
    logger.info(f"Password changed for user: {current_user.email}")
    
    return {"message": "Password successfully changed"}

@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    request_data: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """Запрос на восстановление пароля (отправка email с токеном)"""
    
    # Поиск пользователя
    user = db.query(User).filter(User.email == request_data.email).first()
    
    # Всегда возвращаем успех, чтобы не раскрывать существование email
    if not user:
        logger.warning(f"Password reset requested for non-existent email: {request_data.email}")
        return {"message": "If the email exists, a reset link has been sent"}
    
    # Генерация токена
    token = generate_reset_token()
    expires_at = datetime.utcnow() + timedelta(hours=1)  # Токен действителен 1 час
    
    # Сохранение токена в БД
    reset_token = PasswordResetToken(
        user_id=user.id,
        token=token,
        expires_at=expires_at
    )
    db.add(reset_token)
    db.commit()
    
    # Отправка email
    await send_password_reset_email(user.email, token, user.username)
    
    logger.info(f"Password reset token generated for user: {user.email}")
    
    return {"message": "If the email exists, a reset link has been sent"}

@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    reset_data: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """Сброс пароля по токену"""
    
    # Поиск токена
    reset_token = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == reset_data.token
    ).first()
    
    if not reset_token or not reset_token.is_valid():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    # Поиск пользователя
    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Обновление пароля
    user.hashed_password = hash_password(reset_data.new_password)
    
    # Пометка токена как использованного
    reset_token.is_used = True
    
    db.commit()
    
    logger.info(f"Password reset completed for user: {user.email}")
    
    return {"message": "Password successfully reset"}
