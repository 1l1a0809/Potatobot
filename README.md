# 🥔 Potatobot

Telegram-бот для копания картошки с рейтингом игроков. Написан на Python 3.12 + aiogram 3 + asyncpg.

## ✨ Возможности

- 🥔 **Копание картошки** — случайный вес 1-7 кг, раз в час
- 📊 **Статистика** — личный вес, история копок
- 🏆 **Рейтинги** — топ за сутки и общий топ
- ⚡ **Асинхронность** — полностью асинхронный код на asyncpg
- 🐳 **Docker** — готовый к продакшену образ с non-root пользователем
- 📈 **Метрики** — Prometheus `/metrics` эндпоинт
- 🏥 **Health checks** — `/health` и `/ready` для оркестраторов

## 🚀 Быстрый старт

### Локально (без Docker)

```bash
# Клонирование
git clone https://github.com/1l1a0809/Potatobot.git
cd Potatobot

# Виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Зависимости
pip install -r requirements-dev.txt

# Настройка окружения
cp .env.example .env
# Отредактируй .env — добавь BOT_TOKEN и DATABASE_URL

# Запуск
python -m app.main
```

### Через Docker Compose (рекомендуется)

```bash
# Настройка окружения
cp .env.example .env
# Отредактируй .env

# Запуск бота + PostgreSQL
docker-compose up -d

# Логи
docker-compose logs -f bot

# Остановка
docker-compose down
```

### Только бот (внешняя БД)

```bash
docker build -t potatobot .
docker run -d \
  --name potatobot \
  --restart unless-stopped \
  --env-file .env \
  -p 8080:8080 \
  potatobot
```

## ⚙️ Конфигурация

Все настройки через переменные окружения (файл `.env`):

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| **BOT_TOKEN** | Токен бота от @BotFather | *обязательно* |
| **DATABASE_URL** | PostgreSQL DSN (sslmode=require добавляется автоматически) | *обязательно* |
| **DB_POOL_MIN** | Мин. соединений в пуле | 10 |
| **DB_POOL_MAX** | Макс. соединений в пуле | 20 |
| **DIG_COOLDOWN_SECONDS** | Кулдаун между копками (сек) | 3600 (1 час) |
| **DIG_MIN_KG** | Мин. вес картошки | 1.0 |
| **DIG_MAX_KG** | Макс. вес картошки | 7.0 |
| **DIG_PRECISION** | Знаков после запятой | 1 |
| **HISTORY_RETENTION_HOURS** | Хранение истории (часы) | 48 |
| **CLEANUP_INTERVAL_SECONDS** | Интервал очистки (сек) | 3600 |
| **LEADERBOARD_CACHE_TTL** | TTL кэша рейтинга (сек) | 30 |
| **RATE_LIMIT_REQUESTS** | Макс. запросов в окне | 30 |
| **RATE_LIMIT_WINDOW** | Окно rate limit (сек) | 60 |
| **WEB_HOST** | Хост веб-сервера | 0.0.0.0 |
| **WEB_PORT** | Порт веб-сервера | 8080 |
| **LOG_LEVEL** | Уровень логирования | INFO |
| **LOG_FORMAT** | Формат логов (json/console) | json |

## 📋 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Начать / перезапустить |
| `/dig` | 🥔 Выкопать картошку |
| `/my_stats` | 📊 Моя статистика |
| `/my_history` | 📜 История копок (10 последних) |
| `/top_day` | 🏆 Топ-10 за сутки |
| `/top_all` | 🏆 Общий топ-10 |
| `/help` | ❓ Помощь |

## 🏗 Архитектура

```
app/
├── main.py              # Точка входа
├── config.py            # Pydantic Settings
├── database/            # asyncpg + модели
├── handlers/            # Команды бота
│   ├── basic.py         # /start, /help
│   ├── dig.py           # /dig, /my_stats, /my_history
│   └── stats.py         # /top_day, /top_all
├── services/            # Бизнес-логика
│   ├── dig_service.py   # Копание + кэш рейтингов
│   ├── user_service.py  # Пользователи
│   └── cleanup_service.py # Фоновая очистка
├── middleware/          # Aiogram middleware
│   ├── rate_limit.py    # Троттлинг
│   ├── error_handling.py # Единая обработка ошибок
│   └── logging.py       # Логирование запросов
├── utils/               # Утилиты
│   ├── cache.py         # TTL кэш с декоратором
│   ├── formatting.py    # Форматирование
│   ├── validators.py    # Валидация ввода
│   └── logging.py       # Structlog настройка
├── web/                 # aiohttp веб-сервер
│   ├── health.py        # /health, /ready
│   └── metrics.py       # Prometheus /metrics
└── exceptions.py        # Кастомные исключения
```

## 🧪 Тестирование

```bash
# Все тесты с покрытием
pytest

# Только юнит-тесты
pytest -m unit

# С HTML отчётом покрытия
pytest --cov-report=html
# Открыть htmlcov/index.html
```

## 📦 Разработка

```bash
# Установка pre-commit хуков
pre-commit install

# Форматирование
ruff format app tests

# Линтинг
ruff check app tests

# Типы
mypy app

# Всё вместе
make lint
```

**Makefile команды:**
```bash
make help       # Список команд
make install    # Установить зависимости
make test       # Запустить тесты
make lint       # Линт + типы
make format     # Форматирование
make run        # Запуск бота
make docker-build  # Сборка образа
make docker-up     # docker-compose up
make docker-down   # docker-compose down
```

## 📊 Метрики (Prometheus)

Доступны на `:8080/metrics`:

- `potatobot_dig_commands_total{status}` — всего команд /dig
- `potatobot_dig_kg` — вес выкопанной картошки (гистограмма)
- `potatobot_active_users` — активных пользователей за 24ч
- `potatobot_db_query_duration_seconds` — длительность DB запросов
- `potatobot_cache_hits_total{cache_name}` / `cache_misses` — кэш

## 🏥 Health Checks

- `GET /health` — полная проверка (БД + бот)
- `GET /ready` — готовность к трафику
- `GET /` — для Render keep-alive

## 🗄 База данных

Схема создается автоматически при запуске:

```sql
users:
  - user_id (PK)
  - tg_id (UNIQUE)
  - username
  - total_kg
  - last_dig_time
  - created_at

dig_history:
  - dig_id (PK)
  - user_id (FK → users)
  - kg
  - timestamp
```

Индексы на `(user_id, timestamp DESC)` и `timestamp` для быстрых выборок.

## 🔧 Деплой на Render

1. Создай **Web Service** из этого репозитория
2. Build Command: `docker build -t potatobot .`
3. Start Command: `python -m app.main`
4. Environment Variables: добавь все из `.env.example`
5. Health Check Path: `/health`
6. Port: `8080`

## 📝 Лицензия

MIT — делай что хочешь.

---

**Сделано с ❤️ для копания картошки**