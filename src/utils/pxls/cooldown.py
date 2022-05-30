from datetime import timedelta

from utils.setup import db_stats, stats


def sum_up_to_n(n):
    r = 0
    for i in range(n + 1):
        r += i
    return r


def cd_2(stack, cd):
    stackMultiplier = 3
    if stack == 0:
        return cd
    return (cd * stackMultiplier) * (1 + stack + sum_up_to_n(stack - 1))


def time_convert(seconds):
    min, sec = divmod(seconds, 60)
    hour, min = divmod(min, 60)
    if hour == 0:
        return "%02d:%05.2f" % (min, sec)
    else:
        return "%02d:%02d:%05.2f" % (hour, min, sec)


def get_cds(online, multiplier=None):

    cd = stats.get_cd(online, multiplier)
    cds = []
    total = 0
    for i in range(0, 6):
        t = cd_2(i, cd)
        cds.append(t)
        total += t
    return cds


async def get_best_possible(datetime1, datetime2):
    """Find the best amount of pixels possible to place between 2 datetimes and the average cooldown"""
    data = await db_stats.get_general_stat("online_count", datetime1, datetime2)
    online_counts = [int(e[0]) for e in data if e[0] is not None]
    cooldowns = [round(stats.get_cd(count), 2) for count in online_counts]
    average_cooldown = sum(cooldowns) / len(cooldowns)
    nb_seconds = (datetime2 - datetime1) / timedelta(seconds=1)
    best_possible = round(nb_seconds / average_cooldown)
    return (best_possible, average_cooldown)
