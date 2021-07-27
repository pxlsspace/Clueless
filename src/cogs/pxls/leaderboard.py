import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from utils.database import *

from utils.time_converter import *
from utils.arguments_parser import parse_leaderboard_args
from utils.setup import stats
from utils.discord_utils import format_table, format_number, image_to_file
from utils.table_to_image import table_to_image

class PxlsLeaderboard(commands.Cog, name="Pxls Leaderboard"):

    def __init__(self, client):
        self.client = client
        self.stats = stats

    ### Discord commands ###

    # TODO: error when the time frame is before the canvas start
    # or automatically get alltime values
    @commands.command(
        usage = "[name1] [name2] [...] [-canvas] [-lines <number>] [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]",
        description = "Show the all-time or canvas leaderboard.",
        aliases=["ldb"],
        help = """- `[names]`: center the leaderboard on this user and show the difference with the others. If more than one name: compare them together
                  - `[-canvas|-c]`: to get the canvas leaderboard
                  - `[[-lines|-l] <number>]`: number of lines to show, must be less than 40 (default 20)
                  - `[-last ?d?h?m?s]`: Show the leaderboard of the last ? day, ? hour, ? min, ? second"""
        )
    async def leaderboard(self,ctx,*args):
        ''' Shows the pxls.space leaderboard '''

        try:
            param = parse_leaderboard_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')
        username = param["names"]
        nb_line = int(param["lines"])
        canvas_opt = param["canvas"]
        speed_opt = False
        sort_opt = None

        # if a time value is given, we will show the speed during this time
        if param["before"] or param["after"] or param["last"]:
            speed_opt = True
            sort_opt = "speed"
            if param["before"] == None and param["after"] == None:
                date = param["last"]
                input_time = str_to_td(date)
                if not input_time:
                    return await ctx.send(f"❌ Invalid `last` parameter, format must be `?d?h?m?s`.")
                date2 = datetime.now(timezone.utc)
                date1 = round_minutes_down(datetime.now(timezone.utc) - input_time)
            else:
                date1 = param["after"] or datetime(1900,1,1,0,0,0)
                date2 = param["before"] or datetime.now(timezone.utc)
        else:
            date1 = datetime.now(timezone.utc)
            date2 = datetime.now(timezone.utc)

        # check on sort arg
        if not sort_opt:
            sort = 'canvas' if canvas_opt else 'alltime'
        else:
            sort = sort_opt

        # fetch the leaderboard from the database
        ldb = get_pixels_placed_between(date1,date2,canvas_opt,sort,username if len(username)>1 else None)
        date = ldb[0][4]

        # check that we can actually calculate the speed
        if speed_opt and ldb[0][5] == ldb[0][6]:
            return await ctx.send("❌ The time frame given is too short.")

        # trim the leaderboard to only get the lines asked
        if username:
            # looking for the index and pixel count of the given user
            name_index = None
            for index,line in enumerate(ldb):
                name = list(line)[1]
                if speed_opt:
                    pixels = list(line)[3]
                else:
                    pixels = list(line)[2]
                if name == username[0]:
                    name_index = index
                    user_pixels = pixels
                    break
            if name_index == None:
                return await ctx.send("❌ User not found")

            # calucluate the indexes around the user
            min_idx = max(0,(name_index-round(nb_line/2)))
            max_idx = min(len(ldb),name_index+round(nb_line/2)+1)
            # if one of the idx hits the limit, we change the other idx to show more lines
            if min_idx == 0:
                max_idx = min_idx + nb_line
            if max_idx == len(ldb):
                min_idx = max_idx - nb_line
            ldb = ldb[min_idx:max_idx]
        else:
            ldb = ldb[0:nb_line]

        # build the header of the leaderboard
        column_names = ["Rank","Username","Pixels"]
        alignments2 = ['center','center','right']
        if username:
            column_names.append("Diff")
            alignments2.append('left')
        if speed_opt:
            column_names.append("Speed")
            alignments2.append('right')

        # build the content of the leaderboard
        res_ldb = []
        for i in range(len(ldb)):
            
            # add the rank, name and pixels
            if speed_opt:
                res_ldb.append(list(ldb[i][0:2]))
                res_ldb[i].append(ldb[i][3])
            else:
                res_ldb.append(list(ldb[i][0:3]))

            if res_ldb[i][2] != None:
                res_ldb[i][2] = format_number(res_ldb[i][2])
            else:
                res_ldb[i][2] = "???"

            # add the diff values
            if username:
                if speed_opt:
                    diff = user_pixels-ldb[i][3]
                else:
                    diff = user_pixels-ldb[i][2]
                diff = f'{int(diff):,}'.replace(","," ") # convert to string
                res_ldb[i].append(diff)

            # add the speed
            if speed_opt:
                diff_pixels = ldb[i][3] or 0
                diff_time = (ldb[i][6] - ldb[i][5])
                nb_hours = diff_time/timedelta(hours=1)
                speed = diff_pixels/nb_hours
                # show the speed in pixel/day if the time frame is more than a day
                if nb_hours > 24:
                    speed = speed*24
                    res_ldb[i].append(f'{round(speed,1)} px/d')
                else:
                    res_ldb[i].append(f'{round(speed,1)} px/h')

        # format the leaderboard to be printed
        text = ""
        if speed_opt:
            past_time = ldb[0][5]
            recent_time = ldb[0][6]
            text += "\nBetween {} and {} ({})\n".format(
                format_datetime(past_time),
                format_datetime(recent_time),
                td_format(round_minutes_down(recent_time)-round_minutes_down(past_time))
            )
        text +=  f"(last updated: {format_datetime(date,'R')})"

        colors = None
        if username:
            colors = []
            for e in res_ldb:
                if e[1] == username[0]:
                    colors.append("#66c5cc")
                else:
                    colors.append(None)
        img = table_to_image(res_ldb,column_names,alignments2,colors=colors)

        # create a discord embed with the leaderboard and send it
        emb = discord.Embed()
        if speed_opt:
            emb.add_field(name="Speed Leaderboard",value=text)
        elif canvas_opt:
            emb.add_field(name="Canvas Leaderboard",value=text)
        else:
            emb.add_field(name="All-time Leaderboard",value=text)
        file = image_to_file(img,"leaderboard.png",emb)
        await ctx.send(embed=emb,file=file)

    ### Helper functions ###
    @staticmethod
    def get_speed(name:str,date1:datetime,date2:datetime):
        ''' Get the speed of a user between 2 dates (in pixels/hour)

        return:
         - speed: the average speed in pixels/hour between the 2 dates,
         - diff_pixels the number of pixels placed between the 2 dates,
         - past_time: the closest datetime to date1 in the database',
         - recent_time the closest datetime to date2 in the database'''

        if date1 > date2:
            raise ValueError("date1 must be smaller than date2")
        (past_count, past_time,diff) = get_alltime_pxls_count(name,date1)
        (recent_count, recent_time,diff) = get_alltime_pxls_count(name,date2)

        if recent_count == None:
            # try to compare canvas pixels if cant find alltime pixels
            (past_count, past_time,diff) = get_canvas_pxls_count(name,date1)
            (recent_count, recent_time,diff) = get_canvas_pxls_count(name,date2)
            if recent_count == None:
                raise ValueError(f'User **{name}** was not found.')
        if past_time == None:
            raise ValueError(f'No database entry for this time.')
        if past_time == recent_time:
            raise ValueError("The time given is too short.")

        diff_pixels = recent_count - past_count
        diff_time = recent_time - past_time
        nb_hours = diff_time/timedelta(hours=1)
        speed = diff_pixels/nb_hours
        return speed, diff_pixels, past_time, recent_time

def setup(client):
    client.add_cog(PxlsLeaderboard(client))