# Authentication System Documentation

## Новые эндпоинты аутентификации v2

### 1. POST /v2/auth/register
Регистрация нового пользователя

**Request Body:**
```json
{
  "email": "user@example.com",
  "username": "username",
  "password": "password123"
}
```

**Response:** 201 Created
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "username",
  "is_active": true,
  "is_verified": false,
  "created_at": "2025-10-06T19:00:00Z"
}
```

### 2. POST /v2/auth/login
Вход пользователя с установкой httpOnly cookie

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response:** 200 OK
```json
{
  "message": "Successfully logged in"
}
```

**Cookie:** `access_token` (httpOnly, secure, samesite=lax)

### 3. POST /v2/auth/logout
Выход пользователя с удалением cookie

**Response:** 200 OK
```json
{
  "message": "Successfully logged out"
}
```

### 4. GET /v2/auth/me
Получение информации о текущем пользователе

**Headers:** `Authorization: Bearer <token>` или Cookie: `access_token`

**Response:** 200 OK
```json
{
  "id": 1,
  "email": "user@example.com",
  "username": "username",
  "is_active": true,
  "is_verified": false,
  "created_at": "2025-10-06T19:00:00Z"
}
```

### 5. POST /v2/auth/change-password
Смена пароля для авторизованного пользователя

**Headers:** `Authorization: Bearer <token>` или Cookie: `access_token`

**Request Body:**
```json
{
  "old_password": "oldpassword123",
  "new_password": "newpassword123"
}
```

**Response:** 200 OK
```json
{
  "message": "Password successfully changed"
}
```

### 6. POST /v2/auth/forgot-password
Запрос на восстановление пароля (отправка email с токеном)

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Response:** 200 OK
```json
{
  "message": "If the email exists, a reset link has been sent"
}
```

**Note:** В MVP версии токен выводится в консоль. В production нужно интегрировать email сервис.

### 7. POST /v2/auth/reset-password
Сброс пароля по токену

**Request Body:**
```json
{
  "token": "reset_token_from_email",
  "new_password": "newpassword123"
}
```

**Response:** 200 OK
```json
{
  "message": "Password successfully reset"
}
```

## Структура базы данных

### Таблица users
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    username VARCHAR UNIQUE NOT NULL,
    hashed_password VARCHAR NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
```

### Таблица password_reset_tokens
```sql
CREATE TABLE password_reset_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token VARCHAR UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Безопасность

- Пароли хешируются с использованием bcrypt
- JWT токены с алгоритмом HS256
- httpOnly cookies для защиты от XSS
- Secure flag для HTTPS
- SameSite=lax для защиты от CSRF
- Токены сброса пароля действительны 1 час
- Токены доступа действительны 7 дней

## Переменные окружения

Добавьте в `.env`:
```
SECRET_KEY=your-secret-key-change-in-production
DATABASE_URL=sqlite:///./upak.db
FRONTEND_URL=https://upak.space
```

## Инициализация базы данных

```bash
python migrations/init_db.py
```

## Запуск сервера

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Тестирование API

Документация доступна по адресу: http://localhost:8000/docs
