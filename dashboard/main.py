import time
from datetime import datetime, timedelta, date
import pytz

import numpy as np
import pandas as pd
import sqlite3
import streamlit as st

INVERTER_IDs = range(1, 6)
DATABASE_MINUTES = "database/pv_minutes.db"
TABLE_MINUTES = "minutes"
DATABASE_DAYS = "database/pv_days.db"
TABLE_DAYS = "days"

def get_unix_timestamps_day(day_date, timezone="Europe/Zurich"):
    datetime_start = datetime.combine(day_date, datetime.min.time())
    datetime_start = pytz.timezone(timezone).localize(
        datetime_start).astimezone(pytz.utc)
    datetime_end = datetime_start + timedelta(days=1)
    timestamp_start = int(time.mktime(datetime_start.timetuple()))
    timestamp_end = int(time.mktime(datetime_end.timetuple()))
    return timestamp_start, timestamp_end


def load_power_curve_day(date, timezone="Europe/Zurich"):
    timestamp_start, timestamp_end = get_unix_timestamps_day(date, timezone)

    data_day = pd.DataFrame(
        columns=["timestamp", "datetime", "power_all", "yield_all"])
    data_day["timestamp"] = np.arange(timestamp_start, timestamp_end)
    data_day["power_all"] = np.zeros(
        timestamp_end - timestamp_start, dtype=int)
    data_day["yield_all"] = np.zeros(
        timestamp_end - timestamp_start, dtype=int)

    conn = sqlite3.connect(DATABASE_MINUTES)
    for id in INVERTER_IDs:
        data_tmp = pd.read_sql(
            f'SELECT timestamp, power_ac as power_{id}, yield_day as yield_{id} FROM {TABLE_MINUTES} WHERE (timestamp BETWEEN {timestamp_start} AND {timestamp_end}) AND inverter_id = {id}', conn)
        data_tmp = data_tmp.astype(int)
        data_day = data_day.merge(data_tmp)
        data_day["power_all"] += data_day[f"power_{id}"]
        data_day["yield_all"] += data_day[f"yield_{id}"]

    for id, row in data_day.iterrows():
        data_day.at[id, "datetime"] = datetime.fromtimestamp(
            row["timestamp"], tz=pytz.utc).astimezone(pytz.timezone(timezone)).replace(tzinfo=None)

    return data_day


def load_yield_per_days(start_day, end_day, timezone="Europe/Zurich"):
    dates_list = [start_day+timedelta(days=x) for x in range((end_day-start_day).days)]

    df = pd.DataFrame(columns=["date", "yield"])

    conn = sqlite3.connect(DATABASE_DAYS)
    for day in dates_list:
        timestamp_start, timestamp_end = get_unix_timestamps_day(day, timezone)

        data = pd.read_sql(f"SELECT inverter_id, yield_day FROM (SELECT MAX(timestamp), inverter_id, yield_day FROM {TABLE_DAYS} WHERE (timestamp BETWEEN {timestamp_start} AND {timestamp_end}) GROUP BY inverter_id)", conn)
        total_yield = data["yield_day"].sum()

        df = pd.concat([df, pd.DataFrame(data=[[day, total_yield]], columns=["date", "yield"])], ignore_index=True)

    return df

def load_data_period(start_day, end_day, timezone="Europe/Zurich"):
    datetime_start = datetime.combine(start_day, datetime.min.time())
    datetime_start = pytz.timezone(timezone).localize(
    datetime_start).astimezone(pytz.utc)
    datetime_end = datetime.combine(end_day, datetime.max.time())
    datetime_end = pytz.timezone(timezone).localize(
    datetime_end).astimezone(pytz.utc)
    timestamp_start = int(time.mktime(datetime_start.timetuple()))
    timestart_end = int(time.mktime(datetime_end.timetuple()))
    pass


if __name__ == "__main__":

    st.set_page_config(
        page_title="PV dashboard",
        page_icon="☀"
    )
    st.title("PV dashboard")

    # with st.sidebar:
    #     data = load_data_day(datetime.now(tz=pytz.timezone("Europe/Zurich")) - timedelta(days=1))
    #     value_power, value_yield = 0, 0
    #     if len(data) > 0:
    #         value_power = data.iloc[-1]["power_all"]
    #         value_yield = data.iloc[-1]["yield_all"]
    #     st.metric(label="power", value=f'{value_power} W')
    #     st.metric(label="yield", value=f'{value_yield} Wh')
    #     st.text(f"{datetime.now().replace(microsecond=0)}")

    tab_day, tab_week, tab_month, tab_year, tab_all = st.tabs(
        ["day", "week", "month", "year", "all"])

    with tab_day:
        # https://discuss.streamlit.io/t/how-to-work-date-input-with-shortcuts/25377/2
        def _on_click_today():
            st.session_state.day_input = date_today

        def _on_click_left():
            st.session_state.day_input -= timedelta(days=1)

        def _on_click_right():
            st.session_state.day_input += timedelta(days=1)

        col1, col2, col3, col4, cols5 = st.columns([0.7, 2, 1, 1.6, 5])
        date_today = date.today()
        with col1:
            st.button("<", key='day_left', on_click=_on_click_left)
        with col2:
            datetime_day_slected = st.date_input(
                "day input", key="day_input", label_visibility="collapsed")
        with col3:
            st.button("\>", key='day_right', on_click=_on_click_right)
        with col4:
            st.button("today", key='day_today', on_click=_on_click_today)

        if datetime_day_slected > date_today:
            st.warning('Selected day is in the future!', icon="⚠️")
        else:
            data = load_power_curve_day(datetime_day_slected)
            if len(data) == 0:
                st.error("no data found", icon="⚠️")
            else:
                st.metric(label="yield",
                          value=f'{data.iloc[-1]["yield_all"]/1000:.2f} kWh')
                if datetime_day_slected == date_today:
                    st.metric(label="power",
                              value=f'{data.iloc[-1]["power_all"]} W')
                st.line_chart(data, x="datetime", y=[
                              "power_all", "power_1", "power_2", "power_3", "power_4", "power_5"])

    with tab_week:
        def _on_click_week_today():
            st.session_state.week_input = [week_start_day, week_end_day]

        def _on_click_week_left():
            week_start_day = st.session_state.week_input[0] - timedelta(
                days=st.session_state.week_input[0].weekday())
            week_end_day = week_start_day + timedelta(days=6)
            delta = timedelta(days=7)
            st.session_state.week_input = [
                week_start_day - delta, week_end_day - delta]

        def _on_click_week_right():
            week_start_day = st.session_state.week_input[0] - timedelta(
                days=st.session_state.week_input[0].weekday())
            week_end_day = week_start_day + timedelta(days=6)
            delta = timedelta(days=7)
            st.session_state.week_input = [
                week_start_day + delta, week_end_day + delta]

        col1, col2, col3, col4, cols5 = st.columns([0.7, 3.5, 1, 1.6, 3])
        date_today = date.today()
        week_start_day = date_today - timedelta(days=date_today.weekday())
        week_end_day = week_start_day + timedelta(days=6)
        with col1:
            st.button("<", key='week_left', on_click=_on_click_week_left)
        # https://github.com/streamlit/streamlit/issues/6167
        with col2:
            datetime_day_slected = st.date_input("week input", [
                                                 week_start_day, week_end_day], key="week_input", label_visibility="collapsed")
        with col3:
            st.button("\>", key='week_right', on_click=_on_click_week_right)
        with col4:
            st.button("this week", key='week_today',
                      on_click=_on_click_week_today)

        if len(st.session_state.week_input) == 2:
            data = load_yield_per_days(st.session_state.week_input[0], st.session_state.week_input[1])
            if len(data) > 0:
                st.bar_chart(data, x="date", y="yield")
            else:
                st.error("data not found")
        else:
            st.warning("select start and end date")
