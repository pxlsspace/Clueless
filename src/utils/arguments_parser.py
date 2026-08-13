import argparse
from datetime import datetime, timezone

""" Functions to parse more complicated arguments in discord commands"""


class MyParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)
        # raise argparse.ArgumentTypeError(message)


def parse_pixelfont_args(args):
    parser = MyParser(add_help=False)
    parser.add_argument("text", type=str, nargs="*")

    parser.add_argument("-font", type=str, action="store", required=False, default="*")
    parser.add_argument("-color", type=str, nargs="*", action="store", required=False)
    parser.add_argument(
        "-bgcolor", "-bg", nargs="*", type=str, action="store", required=False
    )

    return parser.parse_args(args)


def valid_datetime_type(arg_datetime_str, user_timezone: timezone = None):
    """Check if the given string is a valid datetime"""

    error_msg = "Given time ({}) not valid. Expected format: `YYYY-mm-dd HH:MM`.".format(
        " ".join(arg_datetime_str)
    )
    user_timezone = user_timezone or timezone.utc
    if isinstance(arg_datetime_str, str):
        arg_datetime_str = arg_datetime_str.split(" ")

    if len(arg_datetime_str) == 1:
        if ":" in arg_datetime_str[0]:
            format = "%Y-%m-%d %H:%M"
            arg_datetime_str.insert(0, datetime.now(user_timezone).strftime("%Y-%m-%d"))
        else:
            format = "%Y-%m-%d"
    elif len(arg_datetime_str) == 2:
        format = "%Y-%m-%d %H:%M"
    else:
        raise ValueError(error_msg)

    dt = " ".join(arg_datetime_str)
    try:
        res_dt = datetime.strptime(dt, format)
        res_dt = res_dt.replace(tzinfo=user_timezone)
        return res_dt
    except ValueError:
        raise ValueError(error_msg)


def check_ranks(value):
    ranks = value.split("-")
    if len(ranks) != 2:
        raise argparse.ArgumentTypeError("Format must be like `<rank1>-<rank2>`.")
    rank_low = ranks[0]
    rank_high = ranks[1]
    if not (rank_low.isdigit() and rank_high.isdigit()):
        raise argparse.ArgumentTypeError("The ranks must be numbers.")
    rank_low = int(rank_low)
    rank_high = int(rank_high)
    if rank_low < 1 or rank_high < 1 or rank_low > 1000 or rank_high > 1000:
        raise argparse.ArgumentTypeError("The ranks must be between 1 and 1000.")
    if rank_low > rank_high:
        raise argparse.ArgumentTypeError(
            "The first rank must be smaller than the second one."
        )

    if rank_high - rank_low > 40:
        raise argparse.ArgumentTypeError("The rank range must be less than 40.")

    return (rank_low, rank_high)
