# -*- coding: utf-8 -*-
import datetime
import re

import pythainlp

datetime_regex = r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})'
date_regex = r'(\d{4})-(\d{2})-(\d{2})'
time_regex = r'(\d{2}):(\d{2})'


def str_to_date(s: str):
    # Match pattern: yyyy-MM-dd
    pattern = date_regex
    match = re.search(pattern, s)

    if match:
        year, month, day = match.groups()
        return datetime.date(year=int(year), month=int(month), day=int(day))
    else:
        raise ValueError("No valid date substring found in the input.")


def str_to_dt(s: str):
    # Match pattern: yyyy-MM-ddThh-mm
    pattern = datetime_regex
    match = re.search(pattern, s)

    if match:
        year, month, day, hour, minute = match.groups()
        return datetime.datetime(year=int(year), month=int(month), day=int(day), hour=int(hour), minute=int(minute))
    else:
        raise ValueError("No valid datetime substring found in the input.")


def to_date_str(dt: datetime.datetime | datetime.date) -> str:
    return dt.strftime("%Y-%m-%d")


def to_dt_str(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M")


def formatted_thai_dt(dt):
    return pythainlp.util.thai_strftime(dt_obj=dt, fmt="%Aที่ %-d %B %Y เวลา %H:%M น.")

def formatted_thai_date(dt):
    if isinstance(dt, str):
        dt = str_to_date(dt)
    return pythainlp.util.thai_strftime(dt_obj=dt, fmt="%Aที่ %-d %B %Y")
