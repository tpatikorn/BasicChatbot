# -*- coding: utf-8 -*-
import datetime
import re

import pythainlp

datetime_regex = r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})'
date_regex = r'(\d{4})-(\d{2})-(\d{2})'
time_regex = r'(\d{2}):(\d{2})'


def str_to_date(s: str):
    # Match pattern: yyyy-MM-dd
    match = re.search(date_regex, s)

    if match:
        year, month, day = match.groups()
        return datetime.date(year=int(year), month=int(month), day=int(day))
    else:
        raise ValueError("No valid date substring found in the input.")


def str_to_time(s: str):
    # Match pattern: hh:mm
    match = re.search(time_regex, s)

    if match:
        hour, minute = match.groups()
        return datetime.time(hour=int(hour), minute=int(minute))
    else:
        raise ValueError("No valid date substring found in the input.")

def str_to_dt(s: str):
    # Match pattern: yyyy-MM-ddThh-mm
    match = re.search(datetime_regex, s)

    if match:
        year, month, day, hour, minute = match.groups()
        return datetime.datetime(year=int(year), month=int(month), day=int(day), hour=int(hour), minute=int(minute))
    else:
        raise ValueError("No valid datetime substring found in the input.")


def to_date_str(dt: datetime.datetime | datetime.date) -> str:
    return dt.strftime("%Y-%m-%d")

def to_time_str(dt: datetime.datetime | datetime.time) -> str:
    return dt.strftime("%H:%M")

def to_dt_str(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def formatted_thai_dt(dt):
    return pythainlp.util.thai_strftime(dt_obj=dt, fmt="%Aที่ %-d %B %Y เวลา %H:%M น.")

def formatted_thai_date(dt):
    if isinstance(dt, str):
        dt = str_to_date(dt)
    if isinstance(dt, datetime.date):
        dt = datetime.datetime.combine(dt, datetime.time())
    return pythainlp.util.thai_strftime(dt_obj=dt, fmt="%Aที่ %-d %B %Y")
