import asyncio
import os
import time
import random
from threading import Thread

from flask import Flask

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
# НАСТРОЙКИ
# =========================================================

COOLDOWN = 3600

# История хранится 48 часов.
# /top_day использует только последние 24 часа.
HISTORY_RETENTION = 48 * 3600


# =========================================================
# ПОДКЛЮЧЕНИЕ К POSTGRESQL
# =========================================================

db_pool = ThreadedConnectionPool(
    minconn=1,
    maxconn=5,
    dsn=DATABASE_URL
)


# =========================================================
# СОЗДАНИЕ / НАСТРОЙКА ТАБЛИЦ
# =========================================================

def init_database():

    conn = db_pool.getconn()

    try:

        with conn.cursor() as cursor:

            # -------------------------------------------------
            # USERS
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    total_potatoes DOUBLE PRECISION DEFAULT 0,
                    total_digs BIGINT DEFAULT 0,
                    last_dig BIGINT DEFAULT 0
                )
            """)

            # Если таблица users уже существовала до появления
            # total_digs — добавляем колонку.

            cursor.execute("""
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS total_digs
                BIGINT DEFAULT 0
            """)

            # -------------------------------------------------
            # DIG HISTORY
            # -------------------------------------------------

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dig_history (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount DOUBLE PRECISION NOT NULL,
                    timestamp BIGINT NOT NULL
                )
            """)

            # -------------------------------------------------
            # ИНДЕКСЫ
            # -------------------------------------------------

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_dig_history_timestamp
                ON dig_history(timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_dig_history_user_id
                ON dig_history(user_id)
            """)

            # Индекс для запросов вида:
            #
            # user_id = ...
            # timestamp >= ...

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS
                idx_dig_history_user_timestamp
                ON dig_history(user_id, timestamp)
            """)

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        db_pool.putconn(conn)


# =========================================================
# ОЧИСТКА СТАРОЙ ИСТОРИИ
# =========================================================

def cleanup_old_history():

    conn = db_pool.getconn()

    try:

        cutoff = int(time.time()) - HISTORY_RETENTION

        with conn.cursor() as cursor:

            cursor.execute("""
                DELETE FROM dig_history
                WHERE timestamp < %s
            """, (cutoff,))

            deleted = cursor.rowcount

        conn.commit()

        if deleted > 0:

            print(
                f"🧹 Удалено старых записей истории: {deleted}"
            )

    except Exception as e:

        conn.rollback()

        print(
            f"⚠️ Ошибка очистки старой истории: {e}"
        )

    finally:

        db_pool.putconn(conn)


# =========================================================
# ФОНОВАЯ ОЧИСТКА
# =========================================================

async def history_cleanup_loop():

    while True:

        try:

            # Проверяем историю раз в час.

            await asyncio.sleep(3600)

            cleanup_old_history()

        except asyncio.CancelledError:

            break

        except Exception as e:

            print(
                f"⚠️ Ошибка фоновой очистки: {e}"
            )


# =========================================================
# ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ
# =========================================================

def format_time(seconds):

    minutes = seconds // 60
    hours = minutes // 60
    minutes %= 60

    if hours > 0:
        return f"{hours} ч. {minutes} мин."

    return f"{minutes} мин."


# =========================================================
# ТАБЛИЦА ЛИДЕРОВ
# =========================================================

async def send_top_list(
    message: Message,
    rows: list,
    title: str
):

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

            # -------------------------------------------------
            # ПОЛУЧАЕМ И БЛОКИРУЕМ ИГРОКА
            # -------------------------------------------------

            cursor.execute(
                """
                SELECT
                    total_potatoes,
                    total_digs,
                    last_dig
                FROM users
                WHERE user_id = %s
                FOR UPDATE
                """,
                (user_id,)
            )

            row = cursor.fetchone()

            # -------------------------------------------------
            # ПРОВЕРЯЕМ COOLDOWN
            # -------------------------------------------------

            if row:

                total_potatoes, total_digs, last_dig = row

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
                total_digs = 0

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

            new_total_digs = total_digs + 1

            # -------------------------------------------------
            # СОХРАНЯЕМ ИГРОКА
            # -------------------------------------------------

            if row:

                cursor.execute(
                    """
                    UPDATE users
                    SET
                        username = %s,
                        total_potatoes = %s,
                        total_digs = %s,
                        last_dig = %s
                    WHERE user_id = %s
                    """,
                    (
                        username,
                        new_total,
                        new_total_digs,
                        current_time,
                        user_id
                    )
                )

            else:

                cursor.execute(
                    """
                    INSERT INTO users
                        (
                            user_id,
                            username,
                            total_potatoes,
                            total_digs,
                            last_dig
                        )
                    VALUES
                        (%s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        username,
                        mined,
                        1,
                        current_time
                    )
                )

            # -------------------------------------------------
            # СОХРАНЯЕМ ИСТОРИЮ
            # -------------------------------------------------

            cursor.execute(
                """
                INSERT INTO dig_history
                    (
                        user_id,
                        amount,
                        timestamp
                    )
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

    except Exception as e:

        conn.rollback()

        print(
            f"❌ Ошибка при копке пользователя "
            f"{user_id}: {e}"
        )

        await message.reply(
            "❌ Произошла ошибка при сохранении копки.\n"
            "Попробуй ещё раз."
        )

        raise

    finally:

        db_pool.putconn(conn)

    # ---------------------------------------------------------
    # ОТВЕТ
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

                GROUP BY
                    h.user_id,
                    u.username

                ORDER BY day_total DESC

                LIMIT 10
                """,
                (one_day_ago,)
            )

            rows = cursor.fetchall()

    except Exception as e:

        print(
            f"❌ Ошибка /top_day: {e}"
        )

        await message.reply(
            "❌ Не удалось получить топ.\n"
            "Попробуй ещё раз."
        )

        return

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

    except Exception as e:

        print(
            f"❌ Ошибка /top_all: {e}"
        )

        await message.reply(
            "❌ Не удалось получить топ.\n"
            "Попробуй ещё раз."
        )

        return

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
                    total_digs,
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

            username, total_potatoes, total_digs, last_dig = row

            # -------------------------------------------------
            # КАРТОШКА ЗА 24 ЧАСА
            # -------------------------------------------------

            one_day_ago = int(time.time()) - 24 * 3600

            cursor.execute(
                """
                SELECT
                    COALESCE(SUM(amount), 0)

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

    except Exception as e:

        print(
            f"❌ Ошибка /stats: {e}"
        )

        await message.reply(
            "❌ Не удалось получить статистику.\n"
            "Попробуй ещё раз."
        )

        return

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
        f"<b>{total_digs}</b>\n"
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
# ЗАПУСК
# =========================================================

async def main():

    print("🥔 Запуск картофельного бота...")

    # ---------------------------------------------------------
    # DATABASE
    # ---------------------------------------------------------

    init_database()

    print("✅ PostgreSQL подключён!")
    print("✅ Таблицы проверены!")

    # ---------------------------------------------------------
    # ПЕРВАЯ ОЧИСТКА
    # ---------------------------------------------------------

    cleanup_old_history()

    print("🧹 Старая история проверена!")

    # ---------------------------------------------------------
    # TELEGRAM COMMANDS
    # ---------------------------------------------------------

    await set_commands()

    print("✅ Команды Telegram установлены!")

    # ---------------------------------------------------------
    # ФОНОВАЯ ОЧИСТКА
    # ---------------------------------------------------------

    cleanup_task = asyncio.create_task(
        history_cleanup_loop()
    )

    print(
        "🧹 Автоматическая очистка истории запущена!"
    )

    print("🚜 Бот запущен!")

    try:

        await dp.start_polling(bot)

    finally:

        cleanup_task.cancel()

        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

        db_pool.closeall()

        print(
            "🔌 Соединения PostgreSQL закрыты."
        )


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    keep_alive()

    asyncio.run(main())
