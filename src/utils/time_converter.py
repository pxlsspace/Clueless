from datetime import datetime, timedelta, timezone
import re
import time

''' Helper functions to convert datetime objects '''

def str_to_td(input:str,raw=False):
    ''' Convert a string in the format '`?`y`?`mo`?`w`?`d`?`h`?`m`?`s' to a
     `timedelta` object.
    Return `None` if the string does not match.'''

    time_formats = [
        ("years","(y|year|years)"),
        ("months","(mo|month|months)"),
        ("weeks","(w|week|weeks)"),
        ("days","(d|day|days])"),
        ("hours","(h|hr|hour|hours)"),
        ("minutes","(m|min|minute|minutes)"),
        ("seconds","(s|sec|second|seconds)"),
    ]

    regex = r""
    for t in time_formats:
        regex+=r"((?P<" + t[0] + r">(\d*\.)?\d+?)" + t[1] + r")?"
    regex = re.compile(regex)

    parts = regex.fullmatch(input)
    if not parts:
        return None
    parts = parts.groupdict()

    if raw == True:
        raw = []
        for name,param in parts.items():
            if param:
                if float(param) < 2:
                    # remove the s
                    name = name[:-1]
                raw.append(f"{param} {name}")
        return ", ".join(raw)

    time_params = {}
    for name, param in parts.items():
        if param:
            # convert months and years to day because timedelta doesn't
            # support these time units
            if name == "months":
                name = "days"
                param = float(param)*30
            elif name == "years":
                name = "days"
                param = float(param)*365
            
            try:
                time_params[name] += float(param)
            except KeyError:
                time_params[name] = float(param)
    return timedelta(**time_params)


def format_datetime(dt:datetime,style=None):
    ''' Convert a datetime to a string for presenation in discord
    with this format: `<t:timestamp[:style]>`'''

    # if no timzeone in the date, we assume it's in UTC
    if dt.tzinfo == None:
        dt = dt.replace(tzinfo = timezone.utc)

    ts = int(dt.timestamp())
    if style:
        return f'<t:{ts}:{style}>'
    else:
        return f'<t:{ts}>'
 

def td_format(td_object:timedelta,hide_seconds=False):
    ''' Convert a `timedelta` object to a string in the format:

    `x years, x months, x days, x min, x sec`.'''
    seconds = int(td_object.total_seconds())
    periods = [
        ('year', 60*60*24*365),
        ('month', 60*60*24*30),
        ('day', 60*60*24),
        ('hour', 60*60),
        ('minute', 60),
        ('second', 1)]

    if hide_seconds:
        periods = periods[:-1]
    strings=[]
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value , seconds = divmod(seconds, period_seconds)
            has_s = 's' if period_value > 1 else ''
            strings.append("%s %s%s" % (period_value, period_name, has_s))
    return ", ".join(strings)


def utc_to_local(dt):
    utc_offset = time.localtime().tm_gmtoff/3600
    dt = dt.replace(tzinfo=timezone(timedelta(hours=utc_offset)))

    return dt + timedelta(hours = utc_offset)

def local_to_utc(dt):
    return dt.astimezone(timezone.utc)

def round_minutes(some_datetime: datetime, step=15):
    """ round up to nearest step-minutes (00:29 -> 00:30)"""
    if step > 60:
        raise AttributeError("step must be less than 60")

    change = timedelta(
        minutes= some_datetime.minute % step,
        seconds=some_datetime.second,
        microseconds=some_datetime.microsecond
    )

    if change > timedelta():
        change -= timedelta(minutes=step)

    return some_datetime - change

def round_minutes_down(some_datetime: datetime, step=15):
    """ round down to nearest step-minutes (00:29 -> 00:15) """
    if step > 60:
        raise AttributeError("step must be less than 60")

    change = timedelta(
        minutes= some_datetime.minute % step,
        seconds=some_datetime.second,
        microseconds=some_datetime.microsecond
    )

    return some_datetime - change
