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
        'name': <str> | None,
        'canvas': <Boolean>,
        'lines': <int>,
        'speed': <Boolean>,
        'last': <str> | None,
        'before': <datetime> | None,
        'after': <datetime> | None
    }'''
    parser  = MyParser(add_help=False)
    parser.add_argument('name', type=str, nargs='?',
        help='Center the leaderboard on this user.')
    parser.add_argument('-canvas', '-c', action='store_true', default=False, 
        help="Flag to get the canvas leaderboard.")
    parser.add_argument('-lines',metavar="<number>", action='store', type=int, default=20,
        help="Number of lines to show.")
    #parser.add_argument("-speed",action='store',required=False,nargs="+")

    parser.add_argument('-speed', '-s', action='store_true', default=False, 
    help="Flag to show the speed.")


    res, rest_args = parser.parse_known_args(args)
    if res.speed == True:
        # parse the rest as speed arguments if flag '-speed'
        res_speed = parse_speed_args(rest_args)
        return vars(res) | res_speed
    else:
        
        return vars(res)

def parse_speed_args(args):
    ''' Parse the speed command arguments, return a dictionary with the values parsed:
    
    dict:{
        'last': <str> | None,
        'before': <datetime> | None,
        'after': <datetime> | None
    }'''
    parser  = MyParser(add_help=False)

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

def valid_datetime_type(arg_datetime_str):
    """Check if the given string is a valid datetime"""
    try:
        d = datetime.strptime(arg_datetime_str, "%Y-%m-%d %H:%M")
        d = d.replace(tzinfo=timezone.utc)
        return d
    except ValueError:
        msg = "Given time ({}) not valid. Expected format, `YYYY-mm-dd HH:MM` !".format(arg_datetime_str)
        raise ValueError(msg)    

# type=lambda s: datetime.datetime.strptime(s, '%Y-%m-%d')
def main():
    input = "GrayTurtles -c  -speed -last 2d -after 2000-02-26 12:40"
    args=input.split()
    try:
        options = parse_leaderboard_args(args)
    except ValueError as e:
        print(e)
        print("usage: >leaderboard [name] [-canvas] [-lines <number>] [-speed [-last <?d?h?m?s>] [-before <YYYY-mm-dd HH:MM>] [-after <YYYY-mm-dd HH:MM>]] ")
        print("-")
        return
    '''
    name = options["name"]
    canvas_opt = options["canvas"]
    nb_line = options["lines"]
    speed_args = options["speed"]

    print(name,canvas_opt,nb_line,speed_args)'''
    print(options)
    #parser.print_usage()

if __name__ == "__main__":
    main()

