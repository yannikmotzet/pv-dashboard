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
        counter = 0
        while counter <= 2:
            query = "#0{}0\r\n".format(addr)
            ser.write(query.encode("ascii"))
            ser.flush()
            data = ser.read(100)
            data_split = str(data).split()
            data_split[0] = addr
            if len(data_split) >= 10:
                # TODO check checksum
                return pd.DataFrame(data=[data_split[:10]], columns=list(DATA_COLUMNS))
            counter += 1
        return None


def get_data(addrs):
    # retrieve data from all inverters
    df = pd.DataFrame(columns=list(DATA_COLUMNS))
    df = df.astype(dtype=DATA_COLUMNS)
    for addr in addrs:
        df = pd.concat([df, get_data_by_addr(addr)], ignore_index=True)
    return df


def write_data(data):
    # save data to database
    conn = sqlite3.connect(DATABASE_MINUTES)
    data.to_sql(name=TABLE_MINUTES, con=conn, if_exists='append', index=False)


def minutes_to_days_db():
    date = datetime.now(tz=pytz.timezone("Europe/Zurich"))
    timestamp_start = date.replace(
        hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc)
    timestamp_start = timestamp_start.replace(tzinfo=None)
    timestamp_end = timestamp_start + timedelta(days=1)
    unixtime_start = int(time.mktime(timestamp_start.timetuple()))
    unixtime_end = int(time.mktime(timestamp_end.timetuple()))

    # get max power and yield from DATABASE_MINUTES
    conn_minutes = sqlite3.connect(DATABASE_MINUTES)
    data_minutes = pd.DataFrame()
    for id in INVERTER_IDs:
        data_minutes_tmp = pd.read_sql(f'SELECT inverter_id, MAX(power_dc) AS power_dc_max, MAX(power_ac) AS power_ac_max FROM {TABLE_MINUTES} WHERE (timestamp BETWEEN {unixtime_start} AND {unixtime_end}) AND inverter_id = {id}', conn_minutes)
        data_minutes_tmp = data_minutes_tmp.merge(pd.read_sql(f'SELECT inverter_id, yield_day FROM {TABLE_MINUTES} WHERE timestamp = (SELECT MAX(TIMESTAMP) FROM {TABLE_MINUTES} WHERE timestamp BETWEEN {unixtime_start} AND {unixtime_end} AND inverter_id = {id}) AND inverter_id = {id}', conn_minutes))
        data_minutes = pd.concat([data_minutes, data_minutes_tmp], ignore_index=True)
    timestamp = int(time.mktime(datetime.now().timetuple()))
    data_minutes.insert(
        0, "timestamp", [timestamp] * len(data_minutes.index), allow_duplicates=True)

    # update data in DATABASE_DAYS
    conn_days = sqlite3.connect(DATABASE_DAYS)
    data_days = pd.read_sql(
        f'SELECT * FROM {TABLE_DAYS} WHERE timestamp BETWEEN {unixtime_start} AND {unixtime_end}', conn_days)
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