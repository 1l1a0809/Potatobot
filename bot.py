import asyncio
import os
import time
import random
import sqlite3
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

# ---- МИКРО ВЕБ-СЕРВЕР ДЛЯ ОБХОДА БЛОКИРОВКИ RENDER ----
app = Flask('')

@app.route('/')
def home():
    return "Картофельный бот онлайн!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()
# ----------------------------------------------------

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("ОШИБКА: Переменная окружения BOT_TOKEN не задана!")

bot = Bot(token=TOKEN)
dp = Dispatcher()

conn = sqlite3.connect("potato_game.db")
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, total_potatoes REAL DEFAULT 0, last_dig INTEGER DEFAULT 0)')
cursor.execute('CREATE TABLE IF NOT EXISTS dig_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, timestamp INTEGER)')
conn.commit()

COOLDOWN = 3600

@dp.message(Command("копать"))
async def dig_potato(message: Message):
    user_id = message.from_user.id
    username = message.from_user.full_name or "Фермер"
    current_time = int(time.time())

    cursor.execute("SELECT total_potatoes, last_dig FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row:
        total_potatoes, last_dig = row
        if current_time - last_dig < COOLDOWN:
            time_left = COOLDOWN - (current_time - last_dig)
            await message.reply(f"⏳ Спина ещё ноет! Отдохни ещё {time_left // 60} мин.")
            return
    else:
        total_potatoes = 0

    mined = round(random.uniform(1.0, 7.0), 1)
    new_total = round(total_potatoes + mined, 1)

    cursor.execute('INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?)', (user_id, username, new_total, current_time))
    cursor.execute('INSERT INTO dig_history (user_id, amount, timestamp) VALUES (?, ?, ?)', (user_id, mined, current_time))
    conn.commit()
    await message.reply(f"🥔 Ты выкопал **{mined} кг** картошки!\nВсего: **{new_total} кг**.")

@dp.message(Command("топ_день"))
async def show_top_day(message: Message):
    one_day_ago = int(time.time()) - (24 * 3600)
    cursor.execute('SELECT u.username, SUM(h.amount) as day_total FROM dig_history h JOIN users u ON h.user_id = u.user_id WHERE h.timestamp >= ? GROUP BY h.user_id ORDER BY day_total DESC LIMIT 10', (one_day_ago,))
    await send_top_list(message, cursor.fetchall(), "☀️ Топ за 24 часа")

@dp.message(Command("топ_всего"))
async def show_top_all(message: Message):
    cursor.execute("SELECT username, total_potatoes FROM users ORDER BY total_potatoes DESC LIMIT 10")
    await send_top_list(message, cursor.fetchall(), "🏆 Абсолютный топ")

async def send_top_list(message: Message, rows: list, title: str):
    if not rows:
        await message.reply(f"📊 {title}:\n\nПока пусто.")
        return
    text = f"**{title}:**\n\n"
    for i, row in enumerate(rows, 1):
        text += f"{i}. {row} — {round(row, 1)} кг 🥔\n"
    await message.reply(text, parse_mode="Markdown")

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    keep_alive()  # Включаем наш веб-сервер
    asyncio.run(main())
