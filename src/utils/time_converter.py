from datetime import datetime, timedelta, timezone
import re
import time
from typing import Iterable

from utils.arguments_parser import valid_datetime_type

""" Helper functions to convert datetime objects """


def str_to_td(input: str, raw=False):
    """Convert a string in the format '`?`y`?`mo`?`w`?`d`?`h`?`m`?`s' to a
     `timedelta` object.
    Return `None` if the string does not match."""

    if not isinstance(input, str) and isinstance(input, Iterable):
        input = " ".join(input)
    time_formats = [
        ("years", "(y|year|years)"),
        ("months", "(mo|month|months)"),
        ("weeks", "(w|week|weeks)"),
        ("days", "(d|day|days)"),
        ("hours", "(h|hr|hour|hours)"),
        ("minutes", "(m|min|minute|minutes)"),
        ("seconds", "(s|sec|second|seconds)"),
    ]

    regex = r""
    for t in time_formats:
        regex += r"((?P<" + t[0] + r">(\d*\.)?\d*?)" + t[1] + r")?"
    regex = re.compile(regex)

    parts = regex.fullmatch(input.lower().replace(" ", ""))
    if not parts:
        return None
    parts = parts.groupdict()

    if raw:
        raw = []
        for name, param in parts.items():
            # empty string means 1 (eg: "hour" = "1hour")
            if param is not None:
                if param == "":
                    param = 1
                if float(param) < 2:
                    # remove the s
                    name = name[:-1]
                raw.append(f"{param} {name}")
        return ", ".join(raw)

    time_params = {}
    for name, param in parts.items():
        if param is not None:
            # empty string means 1 (eg: "hour" = "1hour")
            if param == "":
                param = 1

            # convert months and years to day because timedelta doesn't
            # support these time units
            if name == "months":
                name = "days"
                param = float(param) * 30
            elif name == "years":
                name = "days"
                param = float(param) * 365

            try:
                time_params[name] += float(param)
            except KeyError:
                time_params[name] = float(param)
    return timedelta(**time_params)


def format_datetime(dt: datetime, style=None):
    """Convert a datetime to a string for presenation in discord
    with this format: `<t:timestamp[:style]>`"""

    # if no timzeone in the date, we assume it's in UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    ts = int(dt.timestamp())
    if style:
        return f"<t:{ts}:{style}>"
    else:
        return f"<t:{ts}>"


def td_format(
    td_object: timedelta, hide_seconds=False, max_unit="year", short_format=False
):
    """Convert a `timedelta` object to a string in the format:

    `x years, x months, x days, x min, x sec`."""
    seconds = int(td_object.total_seconds())
    periods = [
        ("year", "y", 60 * 60 * 24 * 365),
        ("month", "mo", 60 * 60 * 24 * 30),
        ("day", "d", 60 * 60 * 24),
        ("hour", "h", 60 * 60),
        ("minute", "m", 60),
        ("second", "s", 1),
    ]

    # remove the periods bigger than the "max_unit"
    max_unit_index = 0
    for i, p in enumerate(periods):
        if p[0] != max_unit:
            max_unit_index = i + 1
        else:
            break
    periods = periods[max_unit_index:]
    if hide_seconds:
        periods = periods[:-1]
    strings = []
    for period_name, period_name_short, period_seconds in periods:
        if seconds >= period_seconds:
            period_value, seconds = divmod(seconds, period_seconds)
            has_s = "s" if period_value > 1 and not short_format else ""
            p_name = period_name_short if short_format else " " + period_name
            strings.append("%s%s%s" % (period_value, p_name, has_s))
    if short_format:
        return " ".join(strings)
    else:
        return ", ".join(strings)


def utc_to_local(dt):
    utc_offset = time.localtime().tm_gmtoff / 3600
    dt = dt.replace(tzinfo=timezone(timedelta(hours=utc_offset)))

    return dt + timedelta(hours=utc_offset)


def local_to_utc(dt):
    return dt.astimezone(timezone.utc)


def round_minutes(some_datetime: datetime, step=15):
    """round up to nearest step-minutes (00:29 -> 00:30)"""
    if step > 60:
        raise AttributeError("step must be less than 60")

    change = timedelta(
        minutes=some_datetime.minute % step,
        seconds=some_datetime.second,
        microseconds=some_datetime.microsecond,
    )

    if change > timedelta():
        change -= timedelta(minutes=step)

    return some_datetime - change


def round_minutes_down(some_datetime: datetime, step=15):
    """round down to nearest step-minutes (00:29 -> 00:15)"""
    if step > 60:
        raise AttributeError("step must be less than 60")

    change = timedelta(
        minutes=some_datetime.minute % step,
        seconds=some_datetime.second,
        microseconds=some_datetime.microsecond,
    )

    return some_datetime - change


def format_timezone(tz: timezone) -> str:

    if "UTC" in str(tz).upper():
        utc_offset = ""
    else:
        # UTC offset
        offset = datetime.now(tz).utcoffset().seconds / 3600
        if datetime.now(tz).utcoffset().days < 0:
            offset = offset - 24
        offset_hours = int(offset)
        offset_minutes = int((offset % 1) * 60)

        utc_offset = "UTC{:+d}".format(offset_hours)
        if offset_minutes != 0:
            utc_offset += ":{:02d}".format(offset_minutes)
        utc_offset = f" ({utc_offset})"
    return f"{str(tz)}{utc_offset}"


def get_datetimes_from_input(
    user_timezone: timezone, last=None, before=None, after=None, rounding_step=15
):
    """Get a tuple of 2 timezone aware datetimes corresponding to the user's input.
    Raise ValueError if any error occurrs"""
    if before is None and after is None:
        if last:
            input_time = str_to_td(last)
            if not input_time:
                raise ValueError(
                    "Invalid `last` parameter, format must be `?y?mo?w?d?h?m?s`."
                )
            input_time = input_time + timedelta(minutes=1)
            lower_dt = round_minutes_down(
                datetime.now(timezone.utc) - input_time, step=rounding_step
            )
            higher_dt = datetime.now(timezone.utc)
        else:
            lower_dt = datetime.min.replace(tzinfo=timezone.utc)
            higher_dt = datetime.now(timezone.utc)
    else:
        # Convert the dates to datetime object and check if they are valid
        if after:
            after = valid_datetime_type(
                after.split(" ") if isinstance(after, str) else after, user_timezone
            )
        if before:
            before = valid_datetime_type(
                before.split(" ") if isinstance(before, str) else before, user_timezone
            )

        if after and before and before < after:
            raise ValueError("The 'before' date can't be earlier than the 'after' date.")
        lower_dt = after or datetime.min.replace(tzinfo=timezone.utc)
        higher_dt = before or datetime.now(timezone.utc)

    return (lower_dt, higher_dt)
