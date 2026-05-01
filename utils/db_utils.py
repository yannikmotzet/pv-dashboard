from datetime import datetime, timedelta
import pytz
import sqlite3
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import io

def get_timestamp_from_datetime(date_time, timezone="Europe/Zurich"):
    if date_time.tzinfo is None:
        date_time = pytz.timezone(timezone).localize(
            date_time).astimezone(pytz.utc)
    timestamp = int(date_time.timestamp())
    return timestamp

def get_start_end_timestamps_day(day_date, timezone="Europe/Zurich"):
    datetime_start = datetime.combine(day_date, datetime.min.time())
    timestamp_start = get_timestamp_from_datetime(datetime_start, timezone)
    timestamp_end = get_timestamp_from_datetime(
        datetime_start + timedelta(days=1), timezone)
    return timestamp_start, timestamp_end


def get_latest_pv_data(database, table):
    """
    Retrieves the latest photovoltaic (PV) data from a specified table in the database for each inverter_id.
    Args:
        database (str): The path to the SQLite database file.
        table (str): The name of the table to query.
    Returns:
        pandas.DataFrame: A DataFrame containing the latest PV data for each inverter_id.
                          The DataFrame includes a column 'max_timestamp' representing the latest timestamp.
    """
    with sqlite3.connect(database) as conn:
        data = pd.read_sql(f'SELECT MAX(TIMESTAMP) as max_timestamp, * FROM "{table}" GROUP BY inverter_id', conn)
    return data


def load_power_curve_day(date, database, inverter_ids, timezone="Europe/Zurich"):
    timestamp_start, timestamp_end = get_start_end_timestamps_day(
        date, timezone)
    table_minutes = date.strftime('%Y-%m')

    data_day = pd.DataFrame(
        columns=["timestamp", "datetime", "power_all", "yield_all"])
    data_day["timestamp"] = np.arange(timestamp_start, timestamp_end)
    data_day["power_all"] = np.zeros(
        timestamp_end - timestamp_start, dtype=int)
    data_day["yield_all"] = np.zeros(
        timestamp_end - timestamp_start, dtype=int)

    with sqlite3.connect(database) as conn:
        for id in inverter_ids:
            data_tmp = pd.read_sql(
                f'SELECT timestamp, power_ac as power_{id}, yield_day as yield_{id} FROM "{table_minutes}" WHERE (timestamp BETWEEN {timestamp_start} AND {timestamp_end}) AND inverter_id = {id}', conn)
            data_tmp = data_tmp.astype(int)
            data_day = data_day.merge(data_tmp)
            data_day[f"power_{id}"] /= 1000
            data_day[f"yield_{id}"] /= 1000
            data_day["power_all"] += data_day[f"power_{id}"]
            data_day["yield_all"] += data_day[f"yield_{id}"]

    data_day["datetime"] = pd.to_datetime(data_day["timestamp"], unit='s', utc=True).dt.tz_convert(timezone).dt.tz_localize(None)

    return data_day

def power_curve_to_plot(power_curve, samples=150, inverter_ids=[]):
    # Downsample the data
    if len(power_curve) > samples:
        power_curve = power_curve.iloc[np.linspace(0, len(power_curve) - 1, samples).astype(int)]

    date_str = power_curve["datetime"].iloc[0].strftime('%d.%m.%Y')
    yield_all = power_curve["yield_all"].iloc[-1]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=power_curve["datetime"], y=power_curve["power_all"], mode='lines', name=f'all'))
    for id in inverter_ids:
        yield_inverter = power_curve[f"yield_{id}"].iloc[-1]
        fig.add_trace(go.Scatter(x=power_curve["datetime"], y=power_curve[f"power_{id}"], mode='lines', name=f'{id}: {yield_inverter:.1f} kWh'))

    fig.update_layout(
        title=f'Power Curve {date_str}, yield: {yield_all:.2f} kWh',
        xaxis_title='time',
        yaxis_title='kW',
        template='plotly_white',
        width=600,
        height=400,
    )

    if len(inverter_ids) > 0:
        fig.update_layout(
            legend=dict(
            x=0.01,
            y=0.99,
            xanchor='left',
            yanchor='top',
            bgcolor='rgba(255, 255, 255, 0.5)',
            )
        )

    # save the plot to a BytesIO object
    plot_object = io.BytesIO()
    fig.write_image(plot_object, format='png', engine='kaleido')
    plot_object.seek(0)
    del fig

    return plot_object