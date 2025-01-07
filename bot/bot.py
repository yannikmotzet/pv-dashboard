from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, Application
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import time
import pytz
import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

INVERTER_IDs = range(1, 6)
DATABASE_USERS = "database/users.db"
DATABASE_MINUTES = "database/pv_minutes.db"
DATABASE_DAYS = "database/pv_days.db"

def update_user(chat_id, subscribed=False):
    conn = sqlite3.connect(DATABASE_USERS)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, subscribed INTEGER, joined_at INTEGER, last_update INTEGER, last_message INTEGER)''')
    current_time = int(datetime.now().timestamp())
    cursor.execute('''INSERT OR REPLACE INTO users (chat_id, subscribed, joined_at, last_update, last_message) VALUES (?, ?, COALESCE((SELECT joined_at FROM users WHERE chat_id = ?), ?), ?, ?)''', 
                    (chat_id, int(subscribed), chat_id, current_time, current_time, current_time))
    conn.commit()
    conn.close()

def check_user(chat_id):
    conn = sqlite3.connect(DATABASE_USERS)
    cursor = conn.cursor()
    cursor.execute('''SELECT chat_id FROM users WHERE chat_id = ?''', (chat_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_last_message(chat_id):
    conn = sqlite3.connect(DATABASE_USERS)
    cursor = conn.cursor()
    current_time = int(datetime.now().timestamp())
    cursor.execute('''SELECT name FROM sqlite_master WHERE type='table' AND name='users' ''')
    # in case table or user does not exist
    if cursor.fetchone() is None or cursor.rowcount == 0:
        conn.close()
        update_user(chat_id)
        return
    cursor.execute('''UPDATE users SET last_message = ? WHERE chat_id = ?''', (current_time, chat_id))
    conn.commit()
    conn.close()

def get_subscribed_users():
    conn = sqlite3.connect(DATABASE_USERS)
    cursor = conn.cursor()
    cursor.execute('''SELECT chat_id FROM users WHERE subscribed = 1''')
    users = cursor.fetchall()
    conn.close()
    return users


def get_latest_pv_data():
    timestamp_now = int(datetime.now().timestamp())
    table_minutes = datetime.fromtimestamp(timestamp_now, tz=pytz.timezone("Europe/Zurich")).strftime('%Y-%m')
    conn_minutes = sqlite3.connect(DATABASE_MINUTES)
    data = pd.read_sql(
        f'SELECT * FROM "{table_minutes}" WHERE TIMESTAMP = (SELECT MAX(timestamp) FROM "{table_minutes}" GROUP BY inverter_id) GROUP BY inverter_id', conn_minutes)
    conn_minutes.close()
    return data

def pv_data_to_message(data):
    yield_value = data["yield_day"].sum() / 1000
    power_value = data["power_ac"].sum() / 1000
    timestamp_now = data["timestamp"][0]

    timestamp_str = datetime.fromtimestamp(timestamp_now).strftime('%d.%m.%y %H:%M')
    message = f"yield: *{yield_value:.2f}* kWh\npower: *{power_value:.2f}* kW\n_{timestamp_str}_"
    return message


async def post_init(application: Application) -> None:
    # https://docs.python-telegram-bot.org/en/stable/telegram.ext.applicationbuilder.html#telegram.ext.ApplicationBuilder.post_init
    commands = [
        ("start", "Start daily notifications."),
        ("stop", "Stop daily notifications."),
        ("status", "Get current PV system status")
    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_user(update.effective_chat.id, subscribed=True)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You have successfully subscribed for daily notifications. To unsubscribe use /stop.")
    except Exception as e:
        print(e)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Something went wrong.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_user(update.effective_chat.id, subscribed=False)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You have successfully unsubscribed from daily notifications.")
    except Exception as e:
        print(e)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Something went wrong.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_last_message(update.effective_chat.id)
    except Exception as e:
        print(e)

    try:
        data = get_latest_pv_data()
    except Exception as e:
        print(e)
        exception_message = str(e)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=exception_message)
        return
    
    message = pv_data_to_message(data)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode='Markdown')

async def notification_status(context: ContextTypes.DEFAULT_TYPE):
    try:
        subscribed_users = get_subscribed_users()
    except Exception as e:
        print(e)
        return
    
    # send subscription message when sun is set (last entry in PV database is older than certain threshold)
    min_time_diff = 15 * 60 # sec
    max_time_diff = 30 * 60 + min_time_diff # sec
    data = get_latest_pv_data()
    timestamp_data = data["timestamp"][0]
    timestamp_now = int(datetime.now().timestamp())
    time_difference = timestamp_now - timestamp_data

    # check if the time difference is within the notification window
    if time_difference > min_time_diff and time_difference <= max_time_diff:
        for user in subscribed_users:
            chat_id = user[0]
            message = "*Daily notification*\n"
            message += pv_data_to_message(data)
            message += "\n\nUse /stop to turn off daily notifications."
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')


if __name__ == '__main__':
    with open('bot/telegram.token', 'r') as file:
        chat_token = file.read().strip()

    try:
        application = Application.builder().token(chat_token).post_init(post_init).build()

        start_handler = CommandHandler('start', start)
        stop_handler = CommandHandler('stop', stop)
        status_handler = CommandHandler('status', status)
        application.add_handler(start_handler)
        application.add_handler(stop_handler)
        application.add_handler(status_handler)

        # check every hour for sending status
        job_queue = application.job_queue
        now = datetime.now()
        first_run = datetime(now.year, now.month, now.day, now.hour, now.minute // 30 * 30) + timedelta(minutes=30, seconds=30)
        job_queue.run_repeating(notification_status, interval=timedelta(minutes=30), first=first_run)
        # job_queue.run_repeating(notification_status, interval=timedelta(hours=1), first=timedelta(seconds=10))

        application.run_polling()
    except Exception as e:
        print(e)
        time.sleep(20)
