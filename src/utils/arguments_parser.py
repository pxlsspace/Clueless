import argparse
from datetime import datetime, timezone

''' Functions to parse more complicated arguments in discord commands'''

class MyParser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)
        #raise argparse.ArgumentTypeError(message)   

def parse_leaderboard_args(args):
    ''' Parse the leaderboard command arguments, return a dictionary with the values parsed:

    dict:{
        'names': [<str>] | None,
        'canvas': <Boolean>,
        'lines': <int>,
        'speed': <Boolean>,
        'last': <str> | None,
        'before': <datetime> | None,
        'after': <datetime> | None
    }'''
    parser  = MyParser(add_help=False)
    parser.add_argument('names', type=str, nargs='*',
        help='Center the leaderboard on this user.',default=[])
    parser.add_argument('-canvas', '-c', action='store_true', default=False, 
        help="Flag to get the canvas leaderboard.")
    parser.add_argument('-lines','-l',metavar="<number>", action='store', type=check_lines, default=15,
        help="Number of lines to show.")

    parser.add_argument('-last',action='store',default=None)
    parser.add_argument('-after',
                        dest='after',
                        nargs=2,
                        default=None,
                        help='start datetime in format "YYYY-MM-DD HH:mm"')
    parser.add_argument('-before',
                        dest='before',
                        nargs=2,
                        default=None,
                        help='start datetime in format "YYYY-MM-DD HH:mm"')

    
    res = parser.parse_args(args)
    if res.after:
        after = " ".join(res.after)
        res.after = valid_datetime_type(after)
    if res.before:
        before = " ".join(res.before)
        res.before = valid_datetime_type(before)

    if res.after and res.before and res.before < res.after:
        raise ValueError("The 'before' date can't be earlier than the 'after' date.")
        
    return vars(res)

def parse_speed_args(args):
    ''' Parse the speed command arguments, return a dictionary with the values parsed:
    
    dict:{
        'last': <str> | None,
        'before': <datetime> | None,
        'after': <datetime> | None
    }'''
    parser  = MyParser(add_help=False)
    parser.add_argument('names', type=str, nargs='+',default=[])
    parser.add_argument('-canvas', action='store_true', default=False)
    parser.add_argument("-groupby",choices=['day','hour'],required=False)
    parser.add_argument('-progress', action='store_true', default=False)


    parser.add_argument('-last',action='store',default="1d")
    parser.add_argument('-after',
                        dest='after',
                        nargs=2,
                        default=None,
                        help='start datetime in format "YYYY-MM-DD HH:mm"')
    parser.add_argument('-before',
                        dest='before',
                        nargs=2,
                        default=None,
                        help='start datetime in format "YYYY-MM-DD HH:mm"')

    res = parser.parse_args(args)

    # Convert the args to datetime and check if they are valid
    if res.after:
        after = " ".join(res.after)
        res.after = valid_datetime_type(after)
    if res.before:
        before = " ".join(res.before)
        res.before = valid_datetime_type(before)
    
    if res.after and res.before and res.before < res.after:
        raise ValueError("The 'before' date can't be earlier than the 'after' date.")

    return vars(res)

def parse_outline_args(args):
    parser  = MyParser(add_help=False)

    parser.add_argument('color', type=str, nargs=1,
        help='Color of the outline.')
    parser.add_argument('url', type=str, nargs='?',
        help='URL of the image.')
    parser.add_argument('-sparse', '-thin', action='store_true', default=False,
        help="To get a sparse outline instead of full")
    parser.add_argument('-width',metavar="<number>", action='store', type=int, default=1,
        help="Width of the outline (in pixels)")

    res = parser.parse_args(args)
    return vars(res)

def parse_pixelfont_args(args):
    parser  = MyParser(add_help=False)
    parser.add_argument('text', type=str, nargs="*")
    
    parser.add_argument('-font', type=str, action='store',required=True)
    parser.add_argument('-color', type=str, action='store',required=False,)
    parser.add_argument('-bgcolor',"-bg", type=str, action='store', required=False)

    return parser.parse_args(args)

def valid_datetime_type(arg_datetime_str):
    """Check if the given string is a valid datetime"""
    try:
        d = datetime.strptime(arg_datetime_str, "%Y-%m-%d %H:%M")
        d = d.replace(tzinfo=timezone.utc)
        return d
    except ValueError:
        msg = "Given time ({}) not valid. Expected format: `YYYY-mm-dd HH:MM`.".format(arg_datetime_str)
        raise ValueError(msg)

def check_lines(value):
    try:
        ivalue = int(value)
    except:
        raise argparse.ArgumentTypeError("Must be an integer between 1 and 40.")

    if ivalue <= 0 or ivalue > 40:
        raise argparse.ArgumentTypeError("Must be an integer between 1 and 40.")
    return ivalue
