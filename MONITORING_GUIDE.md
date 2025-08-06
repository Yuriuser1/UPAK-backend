# 📊 Руководство по мониторингу UPAK Backend

## 🎯 Ключевые метрики для мониторинга

### 1. Безопасность
- **HMAC валидация**: Количество успешных/неуспешных проверок webhook'ов
- **Rate limiting**: Количество заблокированных запросов
- **Replay атаки**: Количество обнаруженных повторных запросов
- **Валидация данных**: Количество отклоненных запросов

### 2. Производительность
- **Время ответа**: Средний и максимальный response time
- **Throughput**: Количество запросов в секунду
- **Redis операции**: Время подключения и выполнения команд
- **Telegram Bot**: Время отправки уведомлений

### 3. Надежность
- **Uptime**: Доступность сервиса
- **Error rate**: Процент ошибок
- **Retry операции**: Количество повторных попыток
- **Graceful degradation**: Активация fallback режимов

## 📈 Настройка мониторинга

### 1. Структурированные логи
```python
# Пример лог-записи в JSON формате
{
  "timestamp": "2025-08-06T17:23:25Z",
  "level": "INFO",
  "category": "security",
  "severity": "medium",
  "message": "HMAC validation successful",
  "context": {
    "endpoint": "/yookassa-webhook",
    "user_id": null,
    "request_id": "req_123456",
    "ip_address": "192.168.1.1"
  },
  "performance": {
    "duration_ms": 45,
    "memory_mb": 128
  }
}
```

### 2. Мониторинг Redis
```bash
# Основные команды для мониторинга Redis
redis-cli info stats          # Статистика операций
redis-cli info memory         # Использование памяти
redis-cli info clients        # Подключенные клиенты
redis-cli info replication    # Статус репликации
redis-cli slowlog get 10      # Медленные запросы
```

### 3. Системные метрики
```bash
# CPU и память
htop
free -h
df -h

# Сетевые подключения
netstat -tulpn | grep :8000
ss -tulpn | grep :8000

# Процессы Python
ps aux | grep python
pgrep -f uvicorn
```

## 🚨 Алерты и уведомления

### Критические алерты (немедленное реагирование)
1. **Сервис недоступен** (HTTP 5xx > 5%)
2. **Redis недоступен** (connection errors)
3. **HMAC валидация провалена** (> 10 раз в минуту)
4. **Высокий error rate** (> 10% в течение 5 минут)
5. **Память заканчивается** (> 90% использования)

### Предупреждения (мониторинг)
1. **Высокое время ответа** (> 2 секунд)
2. **Rate limiting активен** (> 50 блокировок в минуту)
3. **Telegram Bot недоступен** (retry attempts)
4. **Диск заполняется** (> 80% использования)
5. **Много медленных запросов Redis** (> 100ms)

## 🔍 Логирование и анализ

### 1. Структура логов
```bash
# Основной лог файл
tail -f logs/upak.log

# Фильтрация по уровню
grep "ERROR" logs/upak.log
grep "CRITICAL" logs/upak.log

# Фильтрация по категории
grep "security" logs/upak.log
grep "telegram" logs/upak.log
grep "database" logs/upak.log
```

### 2. Анализ производительности
```bash
# Медленные запросы
grep "duration_ms.*[5-9][0-9][0-9]" logs/upak.log

# Ошибки по endpoints
grep "error" logs/upak.log | grep -o '"endpoint":"[^"]*"' | sort | uniq -c

# Top IP адреса
grep "ip_address" logs/upak.log | grep -o '"ip_address":"[^"]*"' | sort | uniq -c | sort -nr
```

## 🛠️ Инструменты мониторинга

### Скрипт мониторинга
```bash
#!/bin/bash
# monitoring.sh

echo "=== UPAK Backend Health Check ==="
echo "Timestamp: $(date)"

# Проверка сервиса
if curl -sf http://localhost:8000/health > /dev/null; then
    echo "✅ Service: UP"
else
    echo "❌ Service: DOWN"
fi

# Проверка Redis
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis: UP"
else
    echo "❌ Redis: DOWN"
fi

# Проверка ошибок в логах (последние 5 минут)
ERROR_COUNT=$(grep "ERROR\|CRITICAL" logs/upak.log | grep "$(date -d '5 minutes ago' '+%Y-%m-%d %H:%M')" | wc -l)
echo "⚠️  Errors (last 5 min): $ERROR_COUNT"

# Использование памяти
MEMORY=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
echo "💾 Memory usage: ${MEMORY}%"

echo "=========================="
```

## 🔧 Troubleshooting

### Частые проблемы и решения

1. **Высокое время ответа**
   - Проверить Redis подключение
   - Проверить загрузку CPU/памяти
   - Анализировать медленные запросы

2. **Ошибки HMAC валидации**
   - Проверить YOOKASSA_WEBHOOK_SECRET
   - Проверить системное время
   - Проверить формат входящих данных

3. **Telegram Bot не отвечает**
   - Проверить TELEGRAM_BOT_TOKEN
   - Проверить сетевое подключение
   - Проверить rate limits Telegram API

4. **Redis недоступен**
   - Проверить статус сервиса: `systemctl status redis`
   - Проверить конфигурацию подключения
   - Проверить логи Redis: `/var/log/redis/redis-server.log`

## 📋 Чек-лист ежедневного мониторинга

- [ ] Проверить доступность сервиса
- [ ] Проверить error rate за последние 24 часа
- [ ] Проверить использование ресурсов (CPU, память, диск)
- [ ] Проверить статус Redis
- [ ] Проверить работу Telegram Bot
- [ ] Просмотреть критические ошибки в логах
- [ ] Проверить backup'ы и логи ротации

---
**Обновлено**: 6 августа 2025  
**Версия**: v1.1 для UPAK Backend с полным мониторингом