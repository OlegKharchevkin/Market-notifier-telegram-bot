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
            "INSERT INTO Users (user_id) VALUES (?)", (user_id,))
        connection.commit()
        await message.answer(data["start_message"])


@dp.message(Command("add"))
async def cmd_add(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer(data["wrong_add"])
        return
    try:
        market, article, *description = command.args.split(" ")
        description = " ".join(description)
        article = int(article)
    except ValueError:
        await message.answer(data["wrong_add"])
        return
    if market not in data["markets"]:
        await message.answer(data["wrong_market"])
        return
    info = cursor.execute(
        "SELECT * FROM Products WHERE user_id=? AND market=? AND article=? AND description=?", (message.chat.id, market, article, description))
    if info.fetchone() is None:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url(market, article)) as response:
                try:
                    price = await response.json()
                    price = int(price[-1]["sell_price"])
                except Exception as e:
                    await message.answer(data["wrong_article"])
                    return
        cursor.execute("INSERT INTO Products (user_id, market, article, price, description) VALUES (?, ?, ?, ?, ?)",
                       (message.chat.id, market, article, price, description))
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
        await message.answer(data["article_deleted"])


@dp.message(Command("view"))
async def cmd_view(message: types.Message):
    products = cursor.execute(
        "SELECT market, article, price, description FROM Products WHERE user_id=?", (message.chat.id,))
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
        time = ""
        try:
            time, timezone = command.args.split(" ")
            timezone = int(timezone)
        except ValueError:
            time = command.args
            timezone = cursor.execute(
                "SELECT timezone FROM Users WHERE user_id=?", (message.chat.id,)).fetchone()[0]
        hour, minute = time.split(":")
        hour = int(hour)
        minute = int(minute)
    except ValueError:
        await message.answer(data["wrong_time"])
        return
    if hour < 0 or hour > 23:
        await message.answer(data["wrong_time"])
        return
    if minute < 0 or minute > 59:
        await message.answer(data["wrong_time"])
        return
    scheduler.reschedule_job(
        job_id=str(message.chat.id), trigger="cron", hour=(hour + timezone) % 24, minute=minute)
    cursor.execute("UPDATE Users SET hour=?, minute=?, timezone=? WHERE user_id=?",
                   (hour, minute, timezone, message.chat.id))
    connection.commit()
    await (message.answer(data["time_changed"]))


@dp.message(Command("timezone"))
async def cmd_timezone(message: types.Message, command: CommandObject):
    if command.args is None:
        await message.answer(data["wrong_timezone"])
        return
    try:
        timezone = int(command.args)
    except ValueError:
        await message.answer(data["wrong_timezone"])
        return
    hour, minute = cursor.execute(
        "SELECT hour, minute FROM Users WHERE user_id=?", (message.chat.id,)).fetchone()
    cursor.execute("UPDATE Users SET timezone=? WHERE user_id=?",
                   (timezone, message.chat.id))
    connection.commit()
    scheduler.reschedule_job(job_id=str(message.chat.id), trigger="cron", hour=(
        hour + timezone) % 24, minute=minute)
    await (message.answer(data["timezone_changed"]))


@dp.message(Command("pause"))
async def cmd_pause(message: types.Message):
    cursor.execute("UPDATE Users SET paused=? WHERE user_id=?",
                   (1, message.chat.id))
    connection.commit()
    scheduler.pause_job(job_id=str(message.chat.id))
    await message.answer(data["paused"])


@dp.message(Command("resume"))
async def cmd_resume(message: types.Message):
    cursor.execute("UPDATE Users SET paused=? WHERE user_id=?",
                   (0, message.chat.id))
    connection.commit()
    scheduler.resume_job(job_id=str(message.chat.id))
    await message.answer(data["resumed"])


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(data["help"])


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    hour, minute, timezone, paused = cursor.execute(
        "SELECT hour, minute, timezone, paused FROM users WHERE user_id=?", (user_id,)).fetchone()
    paused = data["off"] if paused else data["on"]
    await message.answer(data["status"].format(hour, minute, timezone, paused))


async def notification(bot: Bot, user_id: int):
    mode = cursor.execute(
        "SELECT mode FROM Users WHERE user_id=?", (user_id,)).fetchone()[0]
    products = cursor.execute(
        "SELECT market, article, price, description FROM Products WHERE user_id=?", (user_id,)).fetchall()
    answers = []
    for market, article, last_price, description in products:
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
            answers.append([market, article, last_price, price, description])
    try:
        if answers != []:
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
        CREATE TABLE IF NOT EXISTS Users (
        user_id INTEGER UNIQUE,
        mode INTEGER NOT NULL DEFAULT 0,
        hour INTEGER NOT NULL DEFAULT 8,
        minute INTEGER NOT NULL DEFAULT 0,
        timezone INTEGER NOT NULL DEFAULT 0,
        paused INTEGER NOT NULL DEFAULT 0)
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS Products (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        market TEXT NOT NULL,
        article INTEGER NOT NULL,
        price INTEGER NOT NULL, 
        description TEXT NOT NULL DEFAULT "")
        ''')
        connection.commit()
        jobs = cursor.execute(
            "SELECT user_id, hour, minute, timezone FROM Users").fetchall()
        for user_id, hour, minute, timezone in jobs:
            scheduler.add_job(notification, trigger='cron',  hour=(hour + timezone) % 24,
                              minute=minute, id=str(user_id), args=(bot, user_id))
        print("ready")
        asyncio.run(main())
    finally:
        connection.close()
