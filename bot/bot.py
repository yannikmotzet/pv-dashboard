from telegram import Update
from telegram.ext import Application, ContextTypes, CommandHandler, Application
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import time
import pytz
import logging
import copy
import utils.db_utils as db_utils

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

INVERTER_IDS = range(1, 6)
DATABASE_USERS = "database/users.db"
DATABASE_MINUTES = "database/pv_minutes.db"
DATABASE_DAYS = "database/pv_days.db"
TIMEZONE = "Europe/Zurich"

def update_user(chat_id, subscribed=False):
    with sqlite3.connect(DATABASE_USERS) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (chat_id INTEGER PRIMARY KEY, subscribed INTEGER, joined_at INTEGER, last_update INTEGER, last_message INTEGER)''')
        current_time = int(datetime.now().timestamp())
        cursor.execute('''INSERT OR REPLACE INTO users (chat_id, subscribed, joined_at, last_update, last_message) VALUES (?, ?, COALESCE((SELECT joined_at FROM users WHERE chat_id = ?), ?), ?, ?)''', 
                        (chat_id, int(subscribed), chat_id, current_time, current_time, current_time))
        conn.commit()

def check_user(chat_id):
    with sqlite3.connect(DATABASE_USERS) as conn:
        cursor = conn.cursor()
        cursor.execute('''SELECT chat_id FROM users WHERE chat_id = ?''', (chat_id,))
        user = cursor.fetchone()
    return user

def update_db_last_message(chat_id):
    with sqlite3.connect(DATABASE_USERS) as conn:
        cursor = conn.cursor()
        current_time = int(datetime.now().timestamp())
        cursor.execute('''SELECT name FROM sqlite_master WHERE type='table' AND name='users' ''')
        # in case table or user does not exist
        if cursor.fetchone() is None or cursor.rowcount == 0:
            update_user(chat_id)
            return
        cursor.execute('''UPDATE users SET last_message = ? WHERE chat_id = ?''', (current_time, chat_id))
        conn.commit()

def get_subscribed_users():
    with sqlite3.connect(DATABASE_USERS) as conn:
        cursor = conn.cursor()
        cursor.execute('''SELECT chat_id FROM users WHERE subscribed = 1''')
        users = cursor.fetchall()
    users = [user[0] for user in users]
    return users


def pv_data_to_message(data, add_yield=True, add_power=True, add_time=True, markdown=True):
    message_parts = []
    
    if add_yield:
        yield_value = data["yield_day"].sum() / 1000
        message_parts.append(f"yield: *{yield_value:.2f}* kWh")
    
    if add_power and "power_ac" in data.columns:
        power_value = data["power_ac"].sum() / 1000
        message_parts.append(f"power: *{power_value:.2f}* kW")
    
    if add_time:
        timestamp_str = datetime.fromtimestamp(data["timestamp"].iloc[-1]).strftime('%d.%m.%y %H:%M')
        message_parts.append(f"_{timestamp_str}_")
    
    message = "\n".join(message_parts)
    
    if not markdown:
        message = message.replace("*", "").replace("_", "")
    
    return message


async def post_init(application: Application) -> None:
    # https://docs.python-telegram-bot.org/en/stable/telegram.ext.applicationbuilder.html#telegram.ext.ApplicationBuilder.post_init
    commands = [
        ("start", "Start daily notifications"),
        ("stop", "Stop daily notifications"),
        ("status", "Get current PV system status"),
        ("day", "Get power curve of the current day"),
        ("month", "Get column chart of yield in current month")

    ]
    await application.bot.set_my_commands(commands)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_user(update.effective_chat.id, subscribed=True)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You have successfully subscribed for daily notifications. To unsubscribe use /stop.")
    except Exception as e:
        logging.error(e)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Something went wrong.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_user(update.effective_chat.id, subscribed=False)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="You have successfully unsubscribed from daily notifications.")
    except Exception as e:
        logging.error(e)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Something went wrong.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_db_last_message(update.effective_chat.id)
    except Exception as e:
        logging.error(e)

    try:
        datetime_now = datetime.now(pytz.timezone(TIMEZONE))
        table_minutes = datetime_now.strftime('%Y-%m')
        latest_data = db_utils.get_latest_pv_data(DATABASE_MINUTES, table_minutes)
        message = pv_data_to_message(latest_data)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode='Markdown')
    except Exception as e:
        logging.error(e)
        exception_message = str(e)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=exception_message)
        return

async def day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_db_last_message(update.effective_chat.id)
    except Exception as e:
        logging.error(e)
    
    try:
        datetime_now = datetime.now(pytz.timezone(TIMEZONE))
        table_minutes = datetime_now.strftime('%Y-%m')
        latest_data = db_utils.get_latest_pv_data(DATABASE_MINUTES, table_minutes)
        message = pv_data_to_message(latest_data)
        timestamp_latest = latest_data["timestamp"].iloc[-1]
        datetime_latest_data = datetime.fromtimestamp(timestamp_latest, tz=pytz.timezone(TIMEZONE))
        
        power_curve = db_utils.load_power_curve_day(datetime_latest_data, DATABASE_MINUTES, INVERTER_IDS)
        if power_curve.empty:
            logging.info("no data found for power curve")
            return
        plot_object = db_utils.power_curve_to_plot(power_curve, inverter_ids=INVERTER_IDS)

        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=copy.copy(plot_object), caption=message, parse_mode='Markdown')
        del plot_object
    except Exception as e:
        logging.error(e)
        return
    
async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        update_db_last_message(update.effective_chat.id)
    except Exception as e:
        logging.error(e)

    message = "This feature is not yet implemented."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def subscription_job(context: ContextTypes.DEFAULT_TYPE):
    # send subscription message when sun is set (last entry in PV database is older than certain threshold)
    min_time_diff = 10 * 60 # sec
    max_time_diff = 30 * 60 + min_time_diff # sec

    datetime_now = datetime.now(pytz.timezone(TIMEZONE))
    table_minutes = datetime_now.strftime('%Y-%m')
    latest_data = db_utils.get_latest_pv_data(DATABASE_MINUTES, table_minutes)
    timestamp_latest = latest_data["timestamp"].iloc[-1]
    timestamp_now = int(datetime_now.timestamp())
    time_difference = timestamp_now - timestamp_latest

    # check if the time difference is within the notification window
    if not(time_difference > min_time_diff and time_difference <= max_time_diff):
        return
    
    try:
        subscribed_users = get_subscribed_users()
    except Exception as e:
        logging.error(e)
        return

    # generate plot
    plot_object = None
    try:
        datetime_now = datetime.now(pytz.timezone(TIMEZONE))
        power_curve = db_utils.load_power_curve_day(datetime_now, DATABASE_MINUTES, INVERTER_IDS)
        if not power_curve.empty:
            plot_object = db_utils.power_curve_to_plot(power_curve, inverter_ids=INVERTER_IDS)
        else:
            logging.info("no data found for power curve")
    except Exception as e:
        logging.error(e)

    message = f"*Daily notification*\n{pv_data_to_message(latest_data, add_power=False)}\n\nUse /stop to turn off daily notifications."

    if plot_object is not None:
        for chat_id in subscribed_users:
            # use copy, send_photo() clears photo object
            await context.bot.send_photo(chat_id=chat_id, photo=copy.copy(plot_object), caption=message, parse_mode='Markdown')
        del plot_object
    else:
        for chat_id in subscribed_users:
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')


if __name__ == '__main__':
    
    with open('bot/telegram.token', 'r') as file:
        chat_token = file.read().strip()

    while True:
        try:
            application = Application.builder().token(chat_token).post_init(post_init).build()

            start_handler = CommandHandler('start', start)
            stop_handler = CommandHandler('stop', stop)
            status_handler = CommandHandler('status', status)
            day_handler = CommandHandler('day', day)
            month_handler = CommandHandler('month', month)
            application.add_handler(start_handler)
            application.add_handler(stop_handler)
            application.add_handler(status_handler)
            application.add_handler(day_handler)
            application.add_handler(month_handler)

            # check every hour for sending status
            job_queue = application.job_queue
            now = datetime.now()
            first_run = datetime(now.year, now.month, now.day, now.hour, now.minute // 30 * 30) + timedelta(minutes=30, seconds=30)
            job_queue.run_repeating(subscription_job, interval=timedelta(minutes=30), first=first_run)

            application.run_polling()
        except Exception as e:
            logging.error(e)
            time.sleep(20)
