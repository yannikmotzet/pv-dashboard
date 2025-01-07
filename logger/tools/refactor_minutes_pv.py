import sqlite3
import os
import pytz
from datetime import datetime

def restructure_database(old_db_path, new_db_path):
    old_conn = sqlite3.connect(old_db_path)
    old_cursor = old_conn.cursor()

    new_conn = sqlite3.connect(new_db_path)
    new_cursor = new_conn.cursor()

    old_cursor.execute("SELECT * FROM minutes")
    rows = old_cursor.fetchall()

    for row in rows:
        timestamp = row[0]
        date = datetime.fromtimestamp(timestamp, tz=pytz.timezone("Europe/Zurich"))
        table_name = date.strftime('%Y-%m')

        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS "{table_name}" (
            timestamp INTEGER,
            inverter_id INTEGER,
            status INTEGER,
            voltage_dc REAL,
            current_dc REAL,
            power_dc INTEGER,
            voltage_ac REAL,
            current_ac REAL,
            power_ac INTEGER,
            temperature INTEGER,
            yield_day INTEGER
        )
        """
        new_cursor.execute(create_table_query)

        insert_query = f"""
        INSERT INTO "{table_name}" (
            timestamp, inverter_id, status, voltage_dc, current_dc, power_dc,
            voltage_ac, current_ac, power_ac, temperature, yield_day
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        new_cursor.execute(insert_query, row)

    new_conn.commit()
    old_conn.close()
    new_conn.close()

old_db_path = '/home/yamo/Downloads/pv_minutes.db'
new_db_path = '/home/yamo/Downloads/pv_minutes_new.db'
restructure_database(old_db_path, new_db_path)