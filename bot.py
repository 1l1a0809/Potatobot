import asyncio
import os
import time
import random
from threading import Thread

from flask import Flask

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

from aiogram import Bot, Dispatcher
from aiogram.types import Message, BotCommand
from aiogram.filters import Command


# =========================================================
# ВЕБ-СЕРВЕР ДЛЯ RENDER
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "🥔 Картофельный бот онлайн!"


def run():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()


# =========================================================
# НАСТРОЙКА БОТА
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError(
        "ОШИБКА: переменная окружения BOT_TOKEN не задана!"
    )


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "ОШИБКА: переменная окружения DATABASE_URL не задана!"
    )


bot = Bot(token=TOKEN)
dp = Dispatcher()


# =========================================================
# ПОДКЛЮЧЕНИЕ К POSTGRESQL
# =========================================================

db_pool = ThreadedConnectionPool(
    minconn=1,
    maxconn=5,
    dsn=DATABASE_URL
)


# =========================================================
# СОЗДАНИЕ ТАБЛИЦ
# =========================================================

def init_database():

    conn = db_pool.getconn()

    try:
        with conn.cursor() as cursor:

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    total_potatoes DOUBLE PRECISION DEFAULT 0,
                    last_dig BIGINT DEFAULT 0
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dig_history (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount DOUBLE PRECISION NOT NULL,
                    timestamp BIGINT NOT NULL
                )
            """)

            # Индекс ускоряет поиск копок за последние 24 часа
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dig_history_timestamp
                ON dig_history(timestamp)
            """)

            # Индекс ускоряет поиск истории конкретного игрока
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_dig_history_user_id
                ON dig_history(user_id)
            """)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        db_pool.putconn(conn)


# =========================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ
# =========================================================

def format_time(seconds):
    """Красиво показывает оставшееся время."""

    minutes = seconds // 60
    hours = minutes // 60
    minutes %= 60

    if hours > 0:
        return f"{hours} ч. {minutes} мин."

    return f"{minutes} мин."


# =========================================================
# ОТПРАВКА ТАБЛИЦЫ ЛИДЕРОВ
# =========================================================

async def send_top_list(message: Message, rows: list, title: str):

    if not rows:

        await message.reply(
            f"📊 <b>{title}</b>\n\n"
            "Пока никто не копал картошку! 🥔",
            parse_mode="HTML"
        )

        return

    text = f"🏆 <b>{title}</b>\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for i, row in enumerate(rows, 1):

        username, amount = row

        if not username:
            username = "Фермер"

        if i <= 3:
            place = medals[i - 1]
        else:
            place = f"<b>{i}.</b>"

        text += (
            f"{place} {username} — "
            f"<b>{amount:.1f} кг</b> 🥔\n"
        )

    await message.reply(
        text,
        parse_mode="HTML"
    )


# =========================================================
# /START
# =========================================================

@dp.message(Command("start"))
async def start_command(message: Message):

    text = (
        "🥔 <b>Картофельная ферма</b>\n\n"

        "Добро пожаловать, фермер!\n"
        "Здесь ты можешь копать картошку и "
        "соревноваться с другими игроками.\n\n"

        "🌱 <b>Доступные команды:</b>\n\n"

        "🥔 /dig — выкопать картошку\n"
        "🏆 /top_day — топ за последние 24 часа\n"
        "👑 /top_all — абсолютный топ\n"
        "📊 /stats — твоя статистика\n\n"

        "⏳ Копать можно раз в час."
    )

    await message.reply(
        text,
        parse_mode="HTML"
    )


# =========================================================
# /DIG
# =========================================================

@dp.message(Command("dig"))
async def dig_potato(message: Message):

    user_id = message.from_user.id
    username = message.from_user.full_name or "Фермер"

    current_time = int(time.time())

    conn = db_pool.getconn()

    try:

        with conn.cursor() as cursor:

            # Получаем игрока
            cursor.execute(
                """
                SELECT total_potatoes, last_dig
                FROM users
                WHERE user_id = %s
                """,
                (user_id,)
            )

            row = cursor.fetchone()

            # -------------------------------------------------
            # ПРОВЕРЯЕМ COOLDOWN
            # -------------------------------------------------

            if row:

                total_potatoes, last_dig = row

                time_passed = current_time - last_dig

                if time_passed < COOLDOWN:

                    time_left = COOLDOWN - time_passed

                    await message.reply(
                        "⏳ <b>Спина ещё ноет!</b>\n\n"
                        f"До следующей копки: "
                        f"<b>{format_time(time_left)}</b> 🥔",
                        parse_mode="HTML"
                    )

                    return

            else:
                total_potatoes = 0

            # -------------------------------------------------
            # КОПАЕМ
            # -------------------------------------------------

            mined = round(
                random.uniform(1.0, 7.0),
                1
            )

            new_total = round(
                total_potatoes + mined,
                1
            )

            # -------------------------------------------------
            # СОХРАНЯЕМ ИГРОКА
            # -------------------------------------------------

            cursor.execute(
                """
                INSERT INTO users
                    (user_id, username, total_potatoes, last_dig)
                VALUES
                    (%s, %s, %s, %s)

                ON CONFLICT (user_id)
                DO UPDATE SET
                    username = EXCLUDED.username,
                    total_potatoes = EXCLUDED.total_potatoes,
                    last_dig = EXCLUDED.last_dig
                """,
                (
                    user_id,
                    username,
                    new_total,
                    current_time
                )
            )

            # -------------------------------------------------
            # СОХРАНЯЕМ ИСТОРИЮ
            # -------------------------------------------------

            cursor.execute(
                """
                INSERT INTO dig_history
                    (user_id, amount, timestamp)
                VALUES
                    (%s, %s, %s)
                """,
                (
                    user_id,
                    mined,
                    current_time
                )
            )

        conn.commit()

    except Exception:

        conn.rollback()

        await message.reply(
            "❌ Произошла ошибка при сохранении копки.\n"
            "Попробуй ещё раз."
        )

        raise

    finally:

        db_pool.putconn(conn)

    # ---------------------------------------------------------
    # ОТВЕТ ИГРОКУ
    # ---------------------------------------------------------

    await message.reply(
        "🥔 <b>Копка завершена!</b>\n\n"

        f"Ты выкопал: <b>{mined:.1f} кг</b>\n"
        f"Всего накоплено: <b>{new_total:.1f} кг</b>\n\n"

        "⏳ Следующая копка через 1 час.",
        parse_mode="HTML"
    )


# =========================================================
# /TOP_DAY
# =========================================================

@dp.message(Command("top_day"))
async def show_top_day(message: Message):

    one_day_ago = int(time.time()) - 24 * 3600

    conn = db_pool.getconn()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    u.username,
                    SUM(h.amount) AS day_total

                FROM dig_history h

                JOIN users u
                    ON h.user_id = u.user_id

                WHERE h.timestamp >= %s

                GROUP BY h.user_id, u.username

                ORDER BY day_total DESC

                LIMIT 10
                """,
                (one_day_ago,)
            )

            rows = cursor.fetchall()

    finally:

        db_pool.putconn(conn)

    await send_top_list(
        message,
        rows,
        "Топ за последние 24 часа"
    )


# =========================================================
# /TOP_ALL
# =========================================================

@dp.message(Command("top_all"))
async def show_top_all(message: Message):

    conn = db_pool.getconn()

    try:

        with conn.cursor() as cursor:

            cursor.execute(
                """
                SELECT
                    username,
                    total_potatoes

                FROM users

                ORDER BY total_potatoes DESC

                LIMIT 10
                """
            )

            rows = cursor.fetchall()

    finally:

        db_pool.putconn(conn)

    await send_top_list(
        message,
        rows,
        "Абсолютный топ"
    )


# =========================================================
# /STATS
# =========================================================

@dp.message(Command("stats"))
async def show_stats(message: Message):

    user_id = message.from_user.id

    conn = db_pool.getconn()

    try:

        with conn.cursor() as cursor:

            # -------------------------------------------------
            # ОСНОВНАЯ ИНФОРМАЦИЯ
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT
                    username,
                    total_potatoes,
                    last_dig

                FROM users

                WHERE user_id = %s
                """,
                (user_id,)
            )

            row = cursor.fetchone()

            if not row:

                await message.reply(
                    "📊 <b>Твоя статистика</b>\n\n"
                    "Ты ещё не копал картошку! 🥔\n\n"
                    "Используй /dig",
                    parse_mode="HTML"
                )

                return

            username, total_potatoes, last_dig = row

            # -------------------------------------------------
            # КОЛИЧЕСТВО КОПОК
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM dig_history
                WHERE user_id = %s
                """,
                (user_id,)
            )

            digs = cursor.fetchone()[0]

            # -------------------------------------------------
            # КАРТОШКА ЗА 24 ЧАСА
            # -------------------------------------------------

            one_day_ago = int(time.time()) - 24 * 3600

            cursor.execute(
                """
                SELECT COALESCE(SUM(amount), 0)

                FROM dig_history

                WHERE user_id = %s
                  AND timestamp >= %s
                """,
                (
                    user_id,
                    one_day_ago
                )
            )

            today = cursor.fetchone()[0]

    finally:

        db_pool.putconn(conn)

    # ---------------------------------------------------------
    # ОТВЕТ
    # ---------------------------------------------------------

    text = (
        "📊 <b>Твоя статистика</b>\n\n"

        f"👨‍🌾 Фермер: <b>{username}</b>\n"
        f"🥔 Всего картошки: "
        f"<b>{total_potatoes:.1f} кг</b>\n"

        f"☀️ За 24 часа: "
        f"<b>{today:.1f} кг</b>\n"

        f"⛏ Всего копок: "
        f"<b>{digs}</b>\n"
    )

    await message.reply(
        text,
        parse_mode="HTML"
    )


# =========================================================
# КОМАНДЫ TELEGRAM
# =========================================================

async def set_commands():

    commands = [

        BotCommand(
            command="start",
            description="Информация о боте"
        ),

        BotCommand(
            command="dig",
            description="Выкопать картошку 🥔"
        ),

        BotCommand(
            command="top_day",
            description="Топ за 24 часа 🏆"
        ),

        BotCommand(
            command="top_all",
            description="Абсолютный топ 👑"
        ),

        BotCommand(
            command="stats",
            description="Моя статистика 📊"
        )
    ]

    await bot.set_my_commands(commands)


# =========================================================
# COOLDOWN
# =========================================================

COOLDOWN = 3600


# =========================================================
# ЗАПУСК
# =========================================================

async def main():

    print("🥔 Запуск картофельного бота...")

    # Создаём таблицы, если их ещё нет
    init_database()

    print("✅ PostgreSQL подключён!")
    print("✅ Таблицы проверены!")

    # Устанавливаем меню команд
    await set_commands()

    print("✅ Команды Telegram установлены!")
    print("🚜 Бот запущен!")

    try:

        await dp.start_polling(bot)

    finally:

        # Закрываем соединения PostgreSQL
        db_pool.closeall()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    keep_alive()

    asyncio.run(main())
