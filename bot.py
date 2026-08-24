import asyncio
import os
import time
import random
import sqlite3
from threading import Thread

from flask import Flask
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
    app.run(host="0.0.0.0", port=8080)


def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()


# =========================================================
# НАСТРОЙКА БОТА
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("ОШИБКА: переменная окружения BOT_TOKEN не задана!")

bot = Bot(token=TOKEN)
dp = Dispatcher()


# =========================================================
# БАЗА ДАННЫХ
# =========================================================

conn = sqlite3.connect("potato_game.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    total_potatoes REAL DEFAULT 0,
    last_dig INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS dig_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    timestamp INTEGER
)
""")

conn.commit()


# =========================================================
# НАСТРОЙКИ
# =========================================================

COOLDOWN = 3600  # 1 час


# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================

def format_time(seconds):
    """Красиво показывает оставшееся время."""

    minutes = seconds // 60
    hours = minutes // 60
    minutes %= 60

    if hours > 0:
        return f"{hours} ч. {minutes} мин."

    return f"{minutes} мин."


async def send_top_list(message: Message, rows: list, title: str):
    """Отправляет красиво оформленный топ."""

    if not rows:
        await message.reply(
            f"📊 <b>{title}</b>\n\n"
            f"Пока никто не копал картошку! 🥔",
            parse_mode="HTML"
        )
        return

    text = f"🏆 <b>{title}</b>\n\n"

    medals = ["🥇", "🥈", "🥉"]

    for i, row in enumerate(rows, 1):

        username, amount = row

        # Если у пользователя нет имени
        if not username:
            username = "Фермер"

        if i <= 3:
            place = medals[i - 1]
        else:
            place = f"<b>{i}.</b>"

        text += f"{place} {username} — <b>{amount:.1f} кг</b> 🥔\n"

    await message.reply(text, parse_mode="HTML")


# =========================================================
# /START
# =========================================================

@dp.message(Command("start"))
async def start_command(message: Message):

    text = (
        "🥔 <b>Картофельная ферма</b>\n\n"
        "Добро пожаловать, фермер!\n"
        "Здесь ты можешь копать картошку и соревноваться "
        "с другими игроками.\n\n"

        "🌱 <b>Доступные команды:</b>\n\n"

        "🥔 /dig — выкопать картошку\n"
        "🏆 /top_day — топ за последние 24 часа\n"
        "👑 /top_all — абсолютный топ\n"
        "📊 /stats — твоя статистика\n\n"

        "⏳ Копать можно раз в час."
    )

    await message.reply(text, parse_mode="HTML")


# =========================================================
# /DIG
# =========================================================

@dp.message(Command("dig"))
async def dig_potato(message: Message):

    user_id = message.from_user.id
    username = message.from_user.full_name or "Фермер"

    current_time = int(time.time())

    cursor.execute(
        "SELECT total_potatoes, last_dig FROM users WHERE user_id = ?",
        (user_id,)
    )

    row = cursor.fetchone()

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

    # Сколько картошки выкопали
    mined = round(random.uniform(1.0, 7.0), 1)

    new_total = round(total_potatoes + mined, 1)

    # Сохраняем пользователя
    cursor.execute(
        """
        INSERT OR REPLACE INTO users
        (user_id, username, total_potatoes, last_dig)
        VALUES (?, ?, ?, ?)
        """,
        (
            user_id,
            username,
            new_total,
            current_time
        )
    )

    # История копки
    cursor.execute(
        """
        INSERT INTO dig_history
        (user_id, amount, timestamp)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            mined,
            current_time
        )
    )

    conn.commit()

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

    cursor.execute(
        """
        SELECT
            u.username,
            SUM(h.amount) AS day_total
        FROM dig_history h
        JOIN users u ON h.user_id = u.user_id
        WHERE h.timestamp >= ?
        GROUP BY h.user_id
        ORDER BY day_total DESC
        LIMIT 10
        """,
        (one_day_ago,)
    )

    rows = cursor.fetchall()

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

    cursor.execute(
        """
        SELECT username, total_potatoes
        FROM users
        ORDER BY total_potatoes DESC
        LIMIT 10
        """
    )

    rows = cursor.fetchall()

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

    cursor.execute(
        """
        SELECT username, total_potatoes, last_dig
        FROM users
        WHERE user_id = ?
        """,
        (user_id,)
    )

    row = cursor.fetchone()

    if not row:

        await message.reply(
            "📊 <b>Твоя статистика</b>\n\n"
            "Ты ещё не копал картошку! 🥔\n"
            "Используй /dig",
            parse_mode="HTML"
        )

        return

    username, total_potatoes, last_dig = row

    # Сколько всего копок
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM dig_history
        WHERE user_id = ?
        """,
        (user_id,)
    )

    digs = cursor.fetchone()[0]

    # Всего выкопано за последние 24 часа
    one_day_ago = int(time.time()) - 24 * 3600

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0)
        FROM dig_history
        WHERE user_id = ?
        AND timestamp >= ?
        """,
        (user_id, one_day_ago)
    )

    today = cursor.fetchone()[0]

    text = (
        "📊 <b>Твоя статистика</b>\n\n"
        f"👨‍🌾 Фермер: <b>{username}</b>\n"
        f"🥔 Всего картошки: <b>{total_potatoes:.1f} кг</b>\n"
        f"☀️ За 24 часа: <b>{today:.1f} кг</b>\n"
        f"⛏ Всего копок: <b>{digs}</b>\n"
    )

    await message.reply(text, parse_mode="HTML")


# =========================================================
# УСТАНОВКА КОМАНД TELEGRAM
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

    print("🥔 Бот запускается...")

    await set_commands()

    print("✅ Команды Telegram установлены!")
    print("🚜 Бот запущен!")

    await dp.start_polling(bot)


if __name__ == "__main__":

    keep_alive()

    asyncio.run(main())
