import asyncio
import os
import time
import random
import sqlite3
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

# Бот автоматически возьмет токен из настроек Koyeb (переменная BOT_TOKEN)
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("ОШИБКА: Переменная окружения BOT_TOKEN не найдена!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Настройка базы данных SQLite
conn = sqlite3.connect("potato_game.db")
cursor = conn.cursor()

# Таблица игроков
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        total_potatoes REAL DEFAULT 0,
        last_dig INTEGER DEFAULT 0
    )
''')

# Таблица истории для топов за день и неделю
cursor.execute('''
    CREATE TABLE IF NOT EXISTS dig_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        timestamp INTEGER
    )
''')
conn.commit()

COOLDOWN = 3600  # Время перезарядки — 1 час (в секундах)


@dp.message(Command("копать"))
async def dig_potato(message: Message):
    user_id = message.from_user.id
    username = message.from_user.full_name or message.from_user.username or "Фермер"
    current_time = int(time.time())

    cursor.execute("SELECT total_potatoes, last_dig FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row:
        total_potatoes, last_dig = row
        time_passed = current_time - last_dig
        
        if time_passed < COOLDOWN:
            time_left = COOLDOWN - time_passed
            minutes = time_left // 60
            seconds = time_left % 60
            await message.reply(f"⏳ Спина ещё ноет от прошлой работы! Отдохни ещё {minutes} мин. {seconds} сек.")
            return
    else:
        total_potatoes = 0

    # Случайный вес картошки от 1.0 до 7.0 кг
    mined = round(random.uniform(1.0, 7.0), 1)
    new_total = round(total_potatoes + mined, 1)

    # Сохраняем в профиль
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, total_potatoes, last_dig)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, new_total, current_time))
    
    # Записываем в историю для временных топов
    cursor.execute('''
        INSERT INTO dig_history (user_id, amount, timestamp)
        VALUES (?, ?, ?)
    ''', (user_id, mined, current_time))
    
    conn.commit()

    await message.reply(f"🥔 Ты взял лопату и выкопал **{mined} кг** картошки!\nВсего у тебя: **{new_total} кг**.")


@dp.message(Command("топ_день"))
async def show_top_day(message: Message):
    current_time = int(time.time())
    one_day_ago = current_time - (24 * 3600)

    cursor.execute('''
        SELECT u.username, SUM(h.amount) as day_total 
        FROM dig_history h
        JOIN users u ON h.user_id = u.user_id
        WHERE h.timestamp >= ?
        GROUP BY h.user_id
        ORDER BY day_total DESC
        LIMIT 10
    ''', (one_day_ago,))
    rows = cursor.fetchall()
    
    await send_top_list(message, rows, "☀️ Топ ударников за последние 24 часа")


@dp.message(Command("топ_неделя"))
async def show_top_week(message: Message):
    current_time = int(time.time())
    one_week_ago = current_time - (7 * 24 * 3600)

    cursor.execute('''
        SELECT u.username, SUM(h.amount) as week_total 
        FROM dig_history h
        JOIN users u ON h.user_id = u.user_id
        WHERE h.timestamp >= ?
        GROUP BY h.user_id
        ORDER BY week_total DESC
        LIMIT 10
    ''', (one_week_ago,))
    rows = cursor.fetchall()
    
    await send_top_list(message, rows, "📅 Топ стахановцев за последние 7 дней")


@dp.message(Command("топ_всего"))
async def show_top_all(message: Message):
    cursor.execute("SELECT username, total_potatoes FROM users ORDER BY total_potatoes DESC LIMIT 10")
    rows = cursor.fetchall()
    
    await send_top_list(message, rows, "🏆 Абсолютный топ фермеров")


async def send_top_list(message: Message, rows: list, title: str):
    if not rows:
        await message.reply(f"📊 {title}:\n\nПоле пустое. Никто ничего не накопал!")
        return

    text = f"**{title}:**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, row in enumerate(rows, 1):
        prefix = medals[i-1] if i <= 3 else f"{i}."
        text += f"{prefix} {row[0]} — {round(row[1], 1)} кг 🥔\n"
        
    await message.reply(text, parse_mode="Markdown")


async def main():
    print("Бот успешно запущен и готов копать!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
