import nest_asyncio
nest_asyncio.apply()

import logging
import asyncio
import json
import datetime
import os
from io import BytesIO

import matplotlib.pyplot as plt
from aiohttp import web

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# ============ Настройка ID админа и отслеживаемого пользователя ============
ADMIN_ID = 1313829356      # Админ
TRACKED_USER_ID = 558505661  # Отслеживаемый пользователь

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Файл для хранения статистики
STATS_FILE = "stats.json"

# Глобальная переменная для хранения chat_id отслеживаемого пользователя
DANILA_CHAT_ID = None

# Определение клавиатуры меню с кнопками
menu_keyboard = ReplyKeyboardMarkup(
    [
        ["✅ Занимался", "❌ Не занимался"],
        ["📊 Статистика", "🏆 Достижения"],
        ["📈 График", "📜 Команды"]
    ],
    resize_keyboard=True
)

# ============ Функции для работы со статистикой ============
def load_stats():
    try:
        with open(STATS_FILE, "r") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_stats(stats):
    with open(STATS_FILE, "w") as file:
        json.dump(stats, file)

def update_stats(user_id: str, did_modeling: bool):
    stats = load_stats()
    today = str(datetime.date.today())
    if user_id not in stats:
        stats[user_id] = {}
    stats[user_id][today] = did_modeling
    save_stats(stats)

# ============ Обработчики команд и сообщений ============
async def start(update: Update, context: CallbackContext):
    global DANILA_CHAT_ID
    user_id = update.message.from_user.id

    # Сохраняем chat_id отслеживаемого пользователя
    if user_id == TRACKED_USER_ID:
        DANILA_CHAT_ID = update.message.chat_id

    await update.message.reply_text(
        f"Привет, {update.message.from_user.first_name}! Я помогу тебе с 3D моделированием. Чем могу помочь?",
        reply_markup=menu_keyboard
    )

async def did_modeling(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id == TRACKED_USER_ID:
        update_stats(str(user_id), True)
        await update.message.reply_text(
            "Отлично! Ты занимался 3D моделированием!",
            reply_markup=menu_keyboard
        )
    else:
        await update.message.reply_text("Вы не отслеживаемый пользователь!", reply_markup=menu_keyboard)

async def did_not_modeling(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    if user_id == TRACKED_USER_ID:
        update_stats(str(user_id), False)
        await update.message.reply_text(
            "Поняла, охуел? Постарайся завтра!",
            reply_markup=menu_keyboard
        )
    else:
        await update.message.reply_text("Вы не отслеживаемый пользователь!", reply_markup=menu_keyboard)

async def stats(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    stats_data = load_stats()
    if user_id == TRACKED_USER_ID or user_id == ADMIN_ID:
        user_stats = stats_data.get(str(TRACKED_USER_ID), {})
        modeling_days = sum(1 for day in user_stats.values() if day)
        total_days = len(user_stats)
        text = f"Занимался 3D {modeling_days} раз за последние {total_days} дней!"
        await update.message.reply_text(text, reply_markup=menu_keyboard)
    else:
        await update.message.reply_text("Вы не админ и не отслеживаемый пользователь!", reply_markup=menu_keyboard)

async def achievements_command(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    stats_data = load_stats()
    if user_id == TRACKED_USER_ID or user_id == ADMIN_ID:
        user_stats = stats_data.get(str(TRACKED_USER_ID), {})
        modeling_days = sum(1 for day in user_stats.values() if day)
        achievement_levels = [
            (1, "Первый шаг: 1 день моделирования"),
            (3, "Новичок: 3 дня моделирования"),
            (5, "Начинающий моделлер: 5 дней моделирования"),
            (10, "Продвинутый моделлер: 10 дней моделирования"),
            (20, "Профи: 20 дней моделирования"),
            (30, "Гуру 3D: 30 дней моделирования"),
            (50, "Мастер: 50 дней моделирования"),
            (70, "Супер Мастер: 70 дней моделирования"),
            (100, "Легенда 3D: 100 дней моделирования")
        ]
        achievements = [text for threshold, text in achievement_levels if modeling_days >= threshold]
        text = ("Твои достижения:\n" + "\n".join(achievements)
                if achievements else "Пока нет достижений. Начни моделировать!")
        await update.message.reply_text(text, reply_markup=menu_keyboard)
    else:
        await update.message.reply_text("Вы не админ и не отслеживаемый пользователь!", reply_markup=menu_keyboard)

async def show_commands(update: Update, context: CallbackContext):
    commands = """
Доступные команды:
/start - Начать общение с ботом
/sdelal - Отметить, что ты занимался моделированием
/ne_zanimalisya - Отметить, что я лох и не занимался моделированием
/statistika - Показать статистику
/dostizheniya - Показать достижения
"""
    await update.message.reply_text(commands, reply_markup=menu_keyboard)

async def plot_stats(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    stats_data = load_stats()
    if user_id == TRACKED_USER_ID or user_id == ADMIN_ID:
        user_stats = stats_data.get(str(TRACKED_USER_ID), {})
        if not user_stats:
            await update.message.reply_text("Нет данных для построения графика.", reply_markup=menu_keyboard)
            return

        sorted_dates = sorted(user_stats.keys())
        x_dates = [datetime.datetime.strptime(date_str, "%Y-%m-%d").date() for date_str in sorted_dates]
        y_values = [1 if user_stats[date_str] else 0 for date_str in sorted_dates]
        cumulative = []
        total = 0
        for val in y_values:
            total += val
            cumulative.append(total)

        plt.figure(figsize=(10, 5))
        plt.plot(x_dates, cumulative, marker='o', linestyle='-')
        plt.title("Прогресс 3D моделирования")
        plt.xlabel("Дата")
        plt.ylabel("Накопленное количество дней")
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()

        await update.message.reply_photo(
            photo=buf,
            caption="График прогресса 3D моделирования",
            reply_markup=menu_keyboard
        )
    else:
        await update.message.reply_text("Вы не админ и не отслеживаемый пользователь!", reply_markup=menu_keyboard)

# ============ Напоминания ============
async def send_reminder(bot):
    if DANILA_CHAT_ID is not None:
        await bot.send_message(DANILA_CHAT_ID, "Не забудь позаниматься 3D моделированием сегодня!")
    else:
        print("DANILA_CHAT_ID не установлен, невозможно отправить напоминание")

def setup_reminders(application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        lambda: application.create_task(send_reminder(application.bot)),
        CronTrigger(hour=20, minute=30, day_of_week='mon,wed')
    )
    scheduler.add_job(
        lambda: application.create_task(send_reminder(application.bot)),
        CronTrigger(hour=19, minute=0, day_of_week='tue,thu,fri')
    )
    scheduler.add_job(
        lambda: application.create_task(send_reminder(application.bot)),
        CronTrigger(hour=14, minute=0, day_of_week='sat,sun')
    )
    scheduler.start()

# ============ Минимальный веб-сервер для Render ============
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    port = int(os.environ.get("PORT", 8000))
    app_http = web.Application()
    app_http.router.add_get('/', handle)
    runner = web.AppRunner(app_http)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ============ Главная функция ============
async def main():
    application = Application.builder().token("xxx").build()

    # Регистрация обработчиков команд и сообщений
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("sdelal", did_modeling))
    application.add_handler(CommandHandler("ne_zanimalisya", did_not_modeling))
    application.add_handler(CommandHandler("statistika", stats))
    application.add_handler(CommandHandler("dostizheniya", achievements_command))
    application.add_handler(CommandHandler("komandy", show_commands))
    application.add_handler(MessageHandler(filters.Regex("^✅ Занимался$"), did_modeling))
    application.add_handler(MessageHandler(filters.Regex("^❌ Не занимался$"), did_not_modeling))
    application.add_handler(MessageHandler(filters.Regex("^📊 Статистика$"), stats))
    application.add_handler(MessageHandler(filters.Regex("^🏆 Достижения$"), achievements_command))
    application.add_handler(MessageHandler(filters.Regex("^📈 График$"), plot_stats))
    application.add_handler(MessageHandler(filters.Regex("^📜 Команды$"), show_commands))

    setup_reminders(application)

    # Запуск веб-сервера для пингов (Render будет посылать запросы по URL)
    await start_web_server()

    # Запуск long polling для Telegram-бота
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
