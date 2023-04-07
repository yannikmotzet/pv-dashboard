from contextlib import contextmanager
import time
from datetime import datetime, timedelta

import pytz
import pandas as pd
import serial
import sqlite3
# import hydra
# from omegaconf import DictConfig, OmegaConf

INVERTER_IDs = range(1, 6)
DATA_COLUMNS = {"inverter_id": int, "status": int, "voltage_dc": float, "current_dc": float, "power_dc": int,
                "voltage_ac": float, "current_ac": float, "power_ac": int, "temperature": int, "yield_day": int}
DATABASE_MINUTES = "database/pv_minutes.db"
TABLE_MINUTES = "minutes"
DATABASE_DAYS = "database/pv_days.db"
TABLE_DAYS = "days"


# TODO config with hydra
# @hydra.main(version_base=None, config_path="config", config_name="config_serial")
@contextmanager
def open_serial():
    # open serial port of RS485 interface
    # print(OmegaConf.to_yaml(cfg))
    ser = serial.Serial(
        "/dev/ttyUSB0",
        9600,
        parity=serial.PARITY_NONE,
        # stopbits=serial.EIGHTBITS,
        timeout=0.5
    )
    try:
        yield ser
    finally:
        ser.close()


def get_data_by_addr(addr):
    # retrieve data from inverter
    # @return id, status, voltage_dc, current_dc, power_dc, voltage_ac, current_ac, power_ac, temp, yield
    with open_serial() as ser:
        fail_counter = 0
        while fail_counter <= 2:
            query = f"#{addr:02d}0\r\n"
            ser.write(query.encode("ascii"))
            ser.flush()
            data = ser.read(100)

            # check checksum
            if sum(data[1:57]) % 256 != int.from_bytes(data[57:58], "little"):
                fail_counter += 1
                continue

            data_split = str(data).split()
            data_split[0] = addr
            return pd.DataFrame(data=[data_split[:10]], columns=list(DATA_COLUMNS))
        return None


def get_data(addrs):
    # retrieve data from all inverters
    df = pd.DataFrame(columns=list(DATA_COLUMNS))
    df = df.astype(dtype=DATA_COLUMNS)
    for addr in addrs:
        data =  get_data_by_addr(addr)
        if data is not None:
            df = pd.concat([df, get_data_by_addr(addr)], ignore_index=True)
    return df


def write_data(data):
    # save data to database
    conn = sqlite3.connect(DATABASE_MINUTES)
    data.to_sql(name=TABLE_MINUTES, con=conn, if_exists='append', index=False)


def minutes_to_days_db():
    datetime_now = datetime.now(tz=pytz.timezone("Europe/Zurich"))
    datetime_start = datetime_now.replace(
        hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc)
    datetime_start = datetime_start.replace(tzinfo=None)
    datetime_end = datetime_start + timedelta(days=1)
    timestamp_start = int(time.mktime(datetime_start.timetuple()))
    timestamp_end = int(time.mktime(datetime_end.timetuple()))

    # get max power and yield from DATABASE_MINUTES
    conn_minutes = sqlite3.connect(DATABASE_MINUTES)
    data_minutes = pd.read_sql(
        f'SELECT inverter_id, MAX(power_dc) AS power_dc_max, MAX(power_ac) AS power_ac_max FROM {TABLE_MINUTES} WHERE (timestamp BETWEEN {timestamp_start} AND {timestamp_end}) GROUP BY inverter_id', conn_minutes)    
    data_minutes = data_minutes.merge(pd.read_sql(
        f'SELECT inverter_id, yield_day FROM (SELECT MAX(timestamp), inverter_id, yield_day FROM {TABLE_MINUTES} WHERE (timestamp BETWEEN {timestamp_start} AND {timestamp_end}) GROUP BY inverter_id)', conn_minutes))
    timestamp = int(time.mktime(datetime.now().timetuple()))
    data_minutes.insert(
        0, "timestamp", [timestamp] * len(data_minutes.index), allow_duplicates=True)

    # update data in DATABASE_DAYS
    conn_days = sqlite3.connect(DATABASE_DAYS)
    data_days = pd.read_sql(
        f'SELECT * FROM {TABLE_DAYS} WHERE timestamp BETWEEN {timestamp_start} AND {timestamp_end}', conn_days)
    if len(data_days) > 0:
        # delete old data
        for index, row in data_days.iterrows():
            conn_days.execute(
                f'DELETE FROM {TABLE_DAYS} WHERE timestamp = {row["timestamp"]} AND inverter_id = {row["inverter_id"]}')
        conn_days.commit()
    data_minutes.to_sql(name=TABLE_DAYS, con=conn_days,
                        if_exists='append', index=False)


if __name__ == "__main__":
    # periodically retrieve data and save to database
    while True:
        data = get_data(INVERTER_IDs)
        if data is not None:
            # insert column with timestamp
            timestamp = int(time.mktime(datetime.now().timetuple()))
            data.insert(0, "timestamp", [timestamp]
                        * len(data.index), allow_duplicates=True)
            data["timestamp"] = data["timestamp"].astype(dtype=int)
            write_data(data)
            try:
                minutes_to_days_db()
            except Exception as e:
                print(e)

        # wait till next minute
        sleeptime = 60 - datetime.utcnow().second
        time.sleep(sleeptime)
