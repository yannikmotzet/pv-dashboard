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
DATABASE_DAYS = "database/pv_days.db"


# TODO config with hydra
# @hydra.main(version_base=None, config_path="config", config_name="config_serial")
@contextmanager
def open_serial():
    # open serial port of RS485 interface
    try:
        ser = serial.Serial(
            "/dev/ttyUSB0",
            9600,
            parity=serial.PARITY_NONE,
            # stopbits=serial.EIGHTBITS,
            timeout=0.5
        )
    except serial.SerialException as e:
        print(f"Failed to open serial port: {e}")
        ser = None

    try:
        if ser:
            yield ser
    finally:
        if ser:
            ser.close()


def get_inverter_data_by_addr(addr):
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
            if len(data_split) >= 10:
                return pd.DataFrame(data=[data_split[:10]], columns=list(DATA_COLUMNS))
            fail_counter += 1
        return None


def get_inverter_data(addrs):
    # retrieve data from all inverters
    df = pd.DataFrame(columns=list(DATA_COLUMNS))
    df = df.astype(dtype=DATA_COLUMNS)
    for addr in addrs:
        data =  get_inverter_data_by_addr(addr)
        if data is not None:
            df = pd.concat([df, get_inverter_data_by_addr(addr)], ignore_index=True)
    if df.empty:
        return None
    return df


def write_to_db(data, database_name, table_name, timeout=20):
    try:
        conn = sqlite3.connect(database_name, timeout=timeout)
        data.to_sql(name=table_name, con=conn, if_exists='append', index=False)
        conn.close()
    except Exception as e:
        print(e)


def export_minutes_to_days_db(timestamp, database_minutes, table_minutes, database_days, table_days):
    timestamp_start, timestamp_end = get_day_start_end(timestamp)

    # get max power and yield from DATABASE_MINUTES
    try:
        conn_minutes = sqlite3.connect(database_minutes, timeout=20)
        data_minutes = pd.read_sql(
            f'SELECT inverter_id, MAX(power_dc) AS power_dc_max, MAX(power_ac) AS power_ac_max FROM "{table_minutes}" WHERE (timestamp BETWEEN {timestamp_start} AND {timestamp_end}) GROUP BY inverter_id', conn_minutes)    
        data_minutes = data_minutes.merge(pd.read_sql(
            f'SELECT timestamp, inverter_id, yield_day FROM (SELECT MAX(timestamp) as timestamp, inverter_id, yield_day FROM "{table_minutes}" WHERE (timestamp BETWEEN {timestamp_start} AND {timestamp_end}) GROUP BY inverter_id)', conn_minutes))
        conn_minutes.close()
    except Exception as e:
        print(e)
        return

    # skip if no data from this day (should not happen because function is triggered after writing to minutes database)
    if data_minutes.empty:
        raise Exception("No data in DATABASE_MINUTES for specific day.")
    
    try:
        conn_days = sqlite3.connect(database_days, timeout=20)
        
        # delete old data
        conn_days.execute(
            f'DELETE FROM "{table_days}" WHERE timestamp BETWEEN {timestamp_start} AND {timestamp_end} AND inverter_id IN ({",".join(map(str, data_minutes["inverter_id"].values))})'
        )
        conn_days.commit()

        # insert new data    
        data_minutes.to_sql(name=table_days, con=conn_days, if_exists='append', index=False)
        conn_days.close()
    except Exception as e:
        print(e)

def write_to_minutes_db(data, database_name, timestamp):
    timestamp_start, timestamp_end = get_day_start_end(timestamp)

    conn_days = sqlite3.connect(database_name, timeout=20)

    # delete old data
    conn_days.execute(
        f'DELETE FROM "{table_days}" WHERE timestamp BETWEEN {timestamp_start} AND {timestamp_end} AND inverter_id IN ({",".join(map(str, data["inverter_id"].values))})'
    )

    # filter for required columns
    data_filtered = data[["timestamp", "inverter_id", "yield_day"]]
    data_filtered = data_filtered.astype(dtype={"timestamp": int, "inverter_id": int, "yield_day": int})
    # add missing columns with NULL values
    for column in conn_days.execute(f'PRAGMA table_info("{table_days}")').fetchall():
        column_name = column[1]
        if column_name not in data_filtered.columns:
            data_filtered[column_name] = None

    # insert new data
    data_filtered.to_sql(name=table_days, con=conn_days, if_exists='append', index=False)
    conn_days.close()


def get_day_start_end(timestamp, tz=pytz.timezone("Europe/Zurich")):
    datetime_day = datetime.fromtimestamp(timestamp, tz=tz)
    datetime_start = datetime_day.replace(
        hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc)
    datetime_end = datetime_start + timedelta(days=1)
    timestamp_start = int(datetime_start.timestamp())
    timestamp_end = int(datetime_end.timestamp())
    return timestamp_start, timestamp_end


if __name__ == "__main__":
    # periodically retrieve data and save to database
    while True:
        data_now = get_inverter_data(INVERTER_IDs)

        if data_now is not None:
            # insert timestamp column
            timestamp_now = int(datetime.now().timestamp())
            data_now.insert(0, "timestamp", [timestamp_now]
                        * len(data_now.index), allow_duplicates=True)
            data_now["timestamp"] = data_now["timestamp"].astype(dtype=int)

            # write to minutes database, table name: YYYY-MM
            table_minutes = datetime.fromtimestamp(timestamp_now, tz=pytz.timezone("Europe/Zurich")).strftime('%Y-%m')
            try:
                write_to_db(data_now, DATABASE_MINUTES, table_minutes)
            except Exception as e:
                print(e)

            # export to days database, table name: YYYY
            table_days = datetime.fromtimestamp(timestamp_now, tz=pytz.timezone("Europe/Zurich")).strftime('%Y')
            try:
                export_minutes_to_days_db(timestamp_now, DATABASE_MINUTES, table_minutes, DATABASE_DAYS, table_days)
            except Exception as e:
                print(e)

                # write data_now to DATABASE_DAYS instead of export from minutes database (max power missing)
                try:
                    write_to_minutes_db(data_now, DATABASE_DAYS, timestamp_now)
                except Exception as e:
                    print(e)


        # wait till next minute
        sleeptime = 60 - datetime.now(pytz.utc).second
        time.sleep(sleeptime)
