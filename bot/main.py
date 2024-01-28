import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types, exceptions
from aiogram.filters import Command, CommandObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import sqlite3
import json
import os

with open("data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

connection = sqlite3.connect("db/users.db")
cursor = connection.cursor()

bot = Bot(token=os.environ.get('TG_TOKEN'))
dp = Dispatcher()

scheduler = AsyncIOScheduler(timezone='Europe/Moscow')


def api_url(market, article):
    return f'https://api.moneyplace.io/client/product/{market}/{article}'


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.chat.id
    info = cursor.execute(
        "SELECT * FROM Users WHERE user_id=?", (user_id,))
    if info.fetchone() is None:
        scheduler.add_job(notification, trigger='cron',  hour=8,
                          minute=0, id=str(user_id), args=(bot, user_id))
        cursor.execute(
            "INSERT INTO Users (user_id, mode, hour, minute) VALUES (?, ?, ?, ?)", (user_id, 0, 8, 0))
        connection.commit()
        await message.answer(data["start_message"])


@dp.message(Command("add"))
async def cmd_add(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer(data["wrong_add"])
        return
    try:
        market, article = command.args.split(" ", maxsplit=1)
        article = int(article)
    except ValueError:
        await message.answer(data["wrong_add"])
        return
    if market not in data["markets"]:
        await message.answer(data["wrong_market"])
        return
    info = cursor.execute(
        "SELECT * FROM Products WHERE user_id=? AND market=? AND article=?", (message.chat.id, market, article))
    if info.fetchone() is None:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url(market, article)) as response:
                try:
                    price = await response.json()
                    price = int(price[-1]["sell_price"])
                except Exception as e:
                    await message.answer(data["wrong_article"])
                    return
        cursor.execute("INSERT INTO Products (user_id, market, article, price) VALUES (?, ?, ?, ?)",
                       (message.chat.id, market, article, price))
        connection.commit()
        await message.answer(data["article_added"])


@dp.message(Command("del"))
async def cmd_del(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer(data["wrong_del"])
        return
    try:
        market, article = command.args.split(" ", maxsplit=1)
        article = int(article)
    except ValueError:
        await message.answer(data["wrong_del"])
        return
    if market not in data["markets"]:
        await message.answer(data["wrong_market"])
        return
    info = cursor.execute(
        "SELECT * FROM Products WHERE user_id=? AND market=? AND article=?",
        (message.chat.id,
         market,
         article)
    )
    if info.fetchone() is not None:
        cursor.execute("DELETE FROM Products WHERE user_id=? AND market=? AND article=?",
                       (message.chat.id, market, article))
        connection.commit()
        await message.answer(data["article_delited"])


@dp.message(Command("view"))
async def cmd_view(message: types.Message):
    products = cursor.execute(
        "SELECT market, article, price FROM Products WHERE user_id=?", (message.chat.id,))
    answer = []
    for article in products:
        answer.append(data["list_element"].format(*article))
    if answer == []:
        await message.answer(data["list_empty"])
    else:
        await message.answer(data["list_header"])
        await message.answer("\n".join(answer))


@dp.message(Command("mode"))
async def cmd_mode(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer(data["wrong_mode"])
        return
    if command.args not in data["modes"]:
        await message.answer(data["wrong_mode"])
        return
    cursor.execute("UPDATE Users SET mode=? WHERE user_id=?",
                   (data["modes"].index(command.args), message.chat.id))
    connection.commit()
    await message.answer(data["mode_changed"])


@dp.message(Command("time"))
async def cmd_time(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer(data["wrong_time"])
        return
    try:
        time, time_zone = command.args.split(" ", maxsplit=1)
        hour, minute = time.split(":")
        hour = int(hour) + int(time_zone.removeprefix("+"))
        minute = int(minute)
    except ValueError:
        await message.answer(data["wrong_time"])
        return
    scheduler.reschedule_job(
        job_id=str(message.chat.id), trigger="cron", hour=hour, minute=minute)
    cursor.execute("UPDATE Users SET hour=?, minute=? WHERE user_id=?",
                   (hour, minute, message.chat.id))
    connection.commit()
    await (message.answer(data["time_changed"]))


@dp.message(Command("pause"))
async def cmd_pause(message: types.Message):
    scheduler.pause_job(job_id=str(message.chat.id))
    await message.answer(data["paused"])


@dp.message(Command("resume"))
async def cmd_resume(message: types.Message):
    scheduler.resume_job(job_id=str(message.chat.id))
    await message.answer(data["resumed"])


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(data["help"])


async def notification(bot: Bot, user_id: int):
    mode = cursor.execute(
        "SELECT mode FROM Users WHERE user_id=?", (user_id,)).fetchone()[0]
    products = cursor.execute(
        "SELECT market, article, price FROM Products WHERE user_id=?", (user_id,)).fetchall()
    answers = []
    for market, article, last_price in products:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url(market, article)) as response:
                try:
                    price = int((await response.json())[-1]["sell_price"])
                except Exception as e:
                    continue
        cursor.execute("UPDATE Products SET price=? WHERE user_id=? AND market=? AND article=?",
                       (price, user_id, market, article))
        connection.commit()
        if mode == 0 or (mode == 1 and last_price != price):
            answers.append([market, article, last_price, price])
    try:
        await bot.send_message(user_id, data["notification_header"])
        await bot.send_message(user_id, "\n".join([data["notification_element"].format(*answer) for answer in answers]))
    except exceptions.TelegramForbiddenError:
        cursor.execute("DELETE FROM Users WHERE user_id=?", (user_id,))
        cursor.execute("DELETE FROM Products WHERE user_id=?", (user_id,))
        connection.commit()


async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS "Users" (
        user_id INTEGER UNIQUE,
        mode INTEGER,
        hour INTEGER,
        minute INTEGER
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Products (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        market TEXT,
        article INTEGER,
        price INTEGER
        )
        ''')
        connection.commit()
        jobs = cursor.execute(
            "SELECT user_id, hour, minute FROM Users").fetchall()
        for user_id, hour, minute in jobs:
            scheduler.add_job(notification, trigger='cron',  hour=hour,
                              minute=minute, id=str(user_id), args=(bot, user_id))
        print("ready")
        asyncio.run(main())
    finally:
        connection.close()
