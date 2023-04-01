from contextlib import contextmanager

import pandas as pd
import numpy as np
import serial
#import hydra
#from omegaconf import DictConfig, OmegaConf

# open serial port of RS485 interface
# TODO config with hydra
#@hydra.main(version_base=None, config_path="config", config_name="config_serial")
@contextmanager
def open_serial():
    #print(OmegaConf.to_yaml(cfg))
    ser = serial.Serial(
        "/dev/ttyUSB",
        9600
    )
    try:
        yield ser
    finally:
        ser.close()

# retrieve data from inverter
def get_data_by_addr(addr):
    with open_serial() as ser:
        query = "#0{}0\r\n".format(addr)
        ser.write(query.encode("ascii"))
        ser.flush()
        data = ser.read(100)
        data_split = str(data).split()
        data_split[0] = addr
        
        # TODO check checksum
        arr = np.array(data_split[:10])
        return arr

# retrieve data from all inverters
def get_data(addrs):
    arr = np.array((len(addrs), 10))
    for addr in addrs:
        pass



# save data to database
def write_data():
    pass



if __name__ == "__main__":
    # periodically retrieve data and save to database
    get_data(range(1, 6))