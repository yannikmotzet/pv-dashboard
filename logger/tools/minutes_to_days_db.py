import time
from datetime import datetime, timedelta

import pytz
import pandas as pd
import serial
import sqlite3

INVERTER_IDs = range(1, 7)
DATABASE_MINUTES = "database/pv_minutes.db"
TABLE_MINUTES = "minutes"
DATABASE_DAYS = "database/pv_days.db"
TABLE_DAYS = "days"

DATE = '2023-04-07 23:59:59'

if __name__ == "__main__":

    if "DATE" not in globals():
        date_time = datetime.now(tz=pytz.timezone("Europe/Zurich"))
    else:
        date_time = datetime.strptime(DATE, "%Y-%m-%d %H:%M:%S")
        date_time = pytz.timezone("Europe/Zurich").localize(
            date_time)

    timestamp_start = date_time.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc)

    timestamp_end = timestamp_start + timedelta(days=1)
    unixtime_start = int(timestamp_start.timestamp())
    unixtime_end = int(timestamp_end.timestamp())

    # get max power and yield from minutes.db
    conn_minutes = sqlite3.connect(DATABASE_MINUTES)
    data_minutes = pd.read_sql(
        f'SELECT inverter_id, MAX(power_dc) AS power_dc_max, MAX(power_ac) AS power_ac_max FROM {TABLE_MINUTES} WHERE (timestamp BETWEEN {unixtime_start} AND {unixtime_end}) GROUP BY inverter_id', conn_minutes)    
    data_minutes = data_minutes.merge(pd.read_sql(
        f'SELECT inverter_id, yield_day FROM (SELECT MAX(timestamp), inverter_id, yield_day FROM {TABLE_MINUTES} WHERE (timestamp BETWEEN {unixtime_start} AND {unixtime_end}) GROUP BY inverter_id)', conn_minutes))
    
    if "DATE" not in globals():
        timestamp = int(datetime.now().timestamp())
    else:
        timestamp = date_time.astimezone(pytz.utc)
        timestamp = int(timestamp.timestamp())

    data_minutes.insert(0, "timestamp", [timestamp] * len(data_minutes.index), allow_duplicates=True)
    print(data_minutes)

    # update data in days.db
    conn_days = sqlite3.connect(DATABASE_DAYS)
    data_days = pd.read_sql(f'SELECT * FROM {TABLE_DAYS} WHERE timestamp BETWEEN {unixtime_start} AND {unixtime_end}', conn_days)
    if len(data_days) > 0:
        print("found existing data")
        print(data_days)
        # delete old data
        for index, row in data_days.iterrows():
            conn_days.execute(f'DELETE FROM {TABLE_DAYS} WHERE timestamp = {row["timestamp"]} AND inverter_id = {row["inverter_id"]}')
        conn_days.commit()

    data_minutes.to_sql(name=TABLE_DAYS, con=conn_days, if_exists='append', index=False)
