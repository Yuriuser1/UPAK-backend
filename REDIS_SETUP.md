# 🔧 Настройка Redis для UPAK Backend

## Зачем нужен Redis?

Redis используется в UPAK Backend для:
- **Защиты от Replay атак** - отслеживание обработанных webhook'ов
- **Rate Limiting** - ограничение количества запросов
- **Кэширования** - улучшение производительности
- **Сессии** - управление пользовательскими сессиями

## Установка Redis

### Ubuntu/Debian
```bash
sudo apt update
sudo apt install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

### CentOS/RHEL
```bash
sudo yum install epel-release
sudo yum install redis
sudo systemctl start redis
sudo systemctl enable redis
```

### macOS (с Homebrew)
```bash
brew install redis
brew services start redis
```

### Docker
```bash
docker run -d --name redis-upak -p 6379:6379 redis:7-alpine
```

## Настройка Redis

### 1. Базовая конфигурация
Отредактируйте файл `/etc/redis/redis.conf`:

```bash
# Привязка к localhost (безопасность)
bind 127.0.0.1

# Порт (по умолчанию 6379)
port 6379

# Пароль (рекомендуется)
requirepass your_strong_password_here

# Максимальная память
maxmemory 256mb
maxmemory-policy allkeys-lru

# Логирование
loglevel notice
logfile /var/log/redis/redis-server.log

# Сохранение данных
save 900 1
save 300 10
save 60 10000
```

### 2. Настройка для продакшена

```bash
# Отключение опасных команд
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command DEBUG ""
rename-command CONFIG ""

# Настройка сети
tcp-keepalive 300
timeout 0

# Производительность
tcp-backlog 511
databases 16
```

### 3. Перезапуск Redis
```bash
sudo systemctl restart redis-server
```

## Проверка работы

### 1. Подключение к Redis CLI
```bash
redis-cli
# Если установлен пароль:
redis-cli -a your_password
```

### 2. Тестовые команды
```redis
# Проверка подключения
PING
# Ответ: PONG

# Установка тестового значения
SET test_key "Hello UPAK"

# Получение значения
GET test_key

# Проверка информации о сервере
INFO server
```

### 3. Проверка из Python
```python
import redis

# Подключение
r = redis.Redis(host='localhost', port=6379, db=0, password='your_password')

# Тест
r.set('upak_test', 'working')
print(r.get('upak_test'))  # b'working'
```

## Настройка в .env файле

```env
# Базовые настройки
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=your_strong_password_here

# Или полный URL
REDIS_URL=redis://:your_password@localhost:6379/0

# Время жизни записей (5 минут)
REDIS_TTL=300
```

## Мониторинг Redis

### 1. Проверка статуса
```bash
sudo systemctl status redis-server
```

### 2. Мониторинг в реальном времени
```bash
redis-cli monitor
```

### 3. Статистика
```bash
redis-cli info stats
```

### 4. Проверка памяти
```bash
redis-cli info memory
```

## Резервное копирование

### 1. Ручное создание снапшота
```bash
redis-cli BGSAVE
```

### 2. Автоматическое резервное копирование
Добавьте в crontab:
```bash
# Резервная копия каждый час
0 * * * * redis-cli BGSAVE

# Копирование файла дампа
5 * * * * cp /var/lib/redis/dump.rdb /backup/redis/dump-$(date +\%Y\%m\%d-\%H\%M).rdb
```

## Безопасность

### 1. Файрвол
```bash
# Разрешить доступ только с localhost
sudo ufw allow from 127.0.0.1 to any port 6379
```

### 2. Пользователи (Redis 6+)
```redis
# Создание пользователя для UPAK
ACL SETUSER upak_user on >strong_password ~* +@all

# Проверка пользователей
ACL LIST
```

### 3. TLS (для продакшена)
```bash
# В redis.conf
tls-port 6380
tls-cert-file /path/to/redis.crt
tls-key-file /path/to/redis.key
tls-ca-cert-file /path/to/ca.crt
```

## Устранение проблем

### 1. Redis не запускается
```bash
# Проверка логов
sudo tail -f /var/log/redis/redis-server.log

# Проверка конфигурации
redis-server /etc/redis/redis.conf --test-config
```

### 2. Проблемы с памятью
```bash
# Очистка всех данных (ОСТОРОЖНО!)
redis-cli FLUSHALL

# Проверка использования памяти
redis-cli info memory
```

### 3. Проблемы с подключением
```bash
# Проверка портов
sudo netstat -tlnp | grep redis

# Проверка процессов
ps aux | grep redis
```

## Fallback режим

Если Redis недоступен, UPAK Backend автоматически переключится на in-memory хранение:
- Защита от replay атак будет работать только в рамках одной сессии
- Rate limiting будет менее точным
- Кэширование будет отключено

⚠️ **Важно**: В продакшене обязательно используйте Redis для обеспечения полной функциональности системы безопасности.