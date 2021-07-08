from datetime import datetime, timedelta, timezone
import re
import time

''' Helper functions to convert datetime objects '''

def str_to_td(input:str):
    ''' Convert a string in the format '`x`d`x`h`x`m`x`s' to a `timedelta` object.
    
    Return `None` if the string does not match.'''

    regex = re.compile(r'((?P<days>\d+?)d)?((?P<hours>\d+?)h)?((?P<minutes>\d+?)(m|min))?((?P<seconds>\d+?)(s|sec))?')
    parts = regex.fullmatch(input)
    if not parts:
        return

    parts = parts.groupdict()
    time_params = {}
    for name, param in parts.items():
        if param:
            time_params[name] = int(param)
    return timedelta(**time_params)


def format_datetime(date:datetime):
    ''' Convert a datetime in a string in this format:
    
    - `today HH:MM (UTC)`
    - `yesterday HH:MM (UTC)`
    - `dd/mm/yyy HH:MM (UTC)` '''
    # set the date to the local utc offset
    utc_offset = time.localtime().tm_gmtoff/3600
    date = date.replace(tzinfo=timezone(timedelta(hours=utc_offset)))
    # convert date to utc
    date = date.astimezone(timezone.utc)
    if date.date() == datetime.now().date():
        date.utcoffset()
        return "today " + date.strftime("%H:%M (%Z)")
    elif date.date() == (datetime.now() - timedelta(days=1)).date():
        return "yesterday " + date.strftime("%H:%M (%Z)")
    else:
        return date.strftime("%d/%m/%Y at %H:%M (%Z)")
 

def td_format(td_object:timedelta):
    ''' Convert a `timedelta` object to a string in the format:

    `x years, x months, x days, x min, x sec`.'''
    seconds = int(td_object.total_seconds())
    periods = [
        ('year', 60*60*24*365),
        ('month', 60*60*24*30),
        ('day', 60*60*24),
        ('hour', 60*60),
        ('minutes', 60),
        ('seconds', 1)]
    strings=[]
    for period_name, period_seconds in periods:
        if seconds >= period_seconds:
            period_value , seconds = divmod(seconds, period_seconds)
            has_s = 's' if period_value > 1 else ''
            strings.append("%s %s%s" % (period_value, period_name, has_s))
    return ", ".join(strings)