from contextlib import contextmanager
import time
from datetime import datetime

import pytz
import pandas as pd
import serial
import sqlite3
# import hydra
# from omegaconf import DictConfig, OmegaConf

INVERTER_IDs = range(1, 6)
DATA_COLUMNS = ["inverter_id", "status", "voltage_dc", "current_dc",
                "power_dc", "voltage_ac", "current_ac", "power_ac", "temperature", "yield_day"]
DATABASE = "pv_database"
TABLE = "pv_monitoring"


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
        #stopbits=serial.EIGHTBITS,
        timeout=0.5
    )
    try:
        yield ser
    finally:
        ser.close()

# retrieve data from inverter
# @return id, status, voltage_dc, current_dc, power_dc, voltage_ac, current_ac, power_ac, temp, yield
def get_data_by_addr(addr):
    # retrieve data from inverter
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
                return pd.DataFrame(data=[data_split[:10]], columns=DATA_COLUMNS)
            counter+=1

        return None


def get_data(addrs):
    # retrieve data from all inverters
    df = pd.DataFrame(columns=DATA_COLUMNS)
    for addr in addrs:
        df = pd.concat([df, get_data_by_addr(addr)], ignore_index=True)    
    return df


def write_data(data, con):
    # save data to database
    data.to_sql(name=TABLE, con=con, if_exists='append', index=False)


if __name__ == "__main__":
    # periodically retrieve data and save to database
    while True:
        con = sqlite3.connect(DATABASE)
        data = get_data(INVERTER_IDs)
        if data is not None:
            # insert column with timestamp
            timestamp = datetime.isoformat(datetime.now(tz=pytz.timezone("Europe/Zurich")))
            data.insert(0, "timestamp", [timestamp] * len(data.index), allow_duplicates=True)
            write_data(data, con)

        # wait till next minute
        sleeptime = 60 - datetime.utcnow().second
        time.sleep(sleeptime)
