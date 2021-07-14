import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from utils.database import *

from utils.time_converter import *
from utils.arguments_parser import parse_leaderboard_args, parse_speed_args
from utils.setup import stats


class PxlsLeaderboard(commands.Cog, name="Pxls Leaderboard"):

    def __init__(self, client):
        self.client = client
        self.stats = stats

    ### Discord commands ###
    @commands.command(usage="<name> [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]",
    description = "Show the average speed of a pxls user.",
    help = """- `<name>`: name of the pxls user
              - `[-last <?d?h?m?s>]`: get the average speed in the last x hours/days/minutes/seconds (default: 1 day)
              - `[-before <date time>]`: to show the average speed before a date and time (format YYYY-mm-dd HH:MM)
              - `[-after <date time>]`: to show the average speed after a date and time (format YYYY-mm-dd HH:MM)"""
    )
    #async def speed(self,ctx,name,time="5h"):
    async def speed(self,ctx,name,*args):
        ''' Show the average speed of a user in the last x min, hours or days '''
        try:
            param = parse_speed_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        if param["before"] == None and param["after"] == None:
            date = param["last"]
            input_time = str_to_td(date)
            if not input_time:
                return await ctx.send(f"❌ Invalid `last` parameter, format must be `{ctx.prefix}{ctx.command.name}{ctx.command.usage}`.")
            recent_time = datetime.now(timezone.utc)
            old_time = datetime.now(timezone.utc) - input_time
        else:
            old_time = param["after"] or datetime(2021,7,7,14,15,10) # To change to oldest database entry
            recent_time = param["before"] or datetime.now(timezone.utc)

        try:
            speed_px_h, diff_pixel, past_time,now_time = self.get_speed(name,old_time,recent_time)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        speed_px_d = round(speed_px_h*24,1)
        speed_px_h = round(speed_px_h,1)
        nb_days = (now_time - past_time)/timedelta(days=1)

        if round(nb_days,1) < 1:
            return await ctx.send(f'**{name}** placed `{diff_pixel}` pixels between {format_datetime(past_time)} and {format_datetime(now_time)}.\nAverage speed: `{speed_px_h}` px/h')
        else:
            return await ctx.send(f'**{name}** placed `{diff_pixel}` pixels between {format_datetime(past_time)} and {format_datetime(now_time)}.\nAverage speed: `{speed_px_h}` px/h or `{speed_px_d}` px/day')

    # TODO: option to show speed in px/day or amount
    # TODO: align speed values on the right
    # TODO: get more accurate date1 value
    @commands.command(
        usage = "[name1] [name2] [...] [-canvas] [-lines <number>] [-speed [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]] [-sort <value>]",
        description = "Show the all-time or canvas leaderboard.",
        aliases=["ldb"],
        help = """- `[names]`: center the leaderboard on this user and show the difference with the others. If more than one name: compare them together
                  - `[-canvas|-c]`: to get the canvas leaderboard
                  - `[[-lines|-l] <number>]`: number of lines to show, must be less than 40 (default 20)
                  - `[-speed ... ]`: add a speed column, see `>help speed` for more information
                  - `[-sort <value>]`: sort the leaderboard either by: `speed`, `canvas` or `alltime`"""
        )
    async def leaderboard(self,ctx,*args):
        ''' Shows the pxls.space leaderboard '''

        try:
            param = parse_leaderboard_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')
        username = param["name"]
        nb_line = param["lines"]
        canvas_opt = param["canvas"]
        speed_opt = param["speed"]
        sort_opt = param["sort"]

        # check on speed args
        if speed_opt:
            if param["before"] == None and param["after"] == None:
                date = param["last"]
                input_time = str_to_td(date)
                if not input_time:
                    return await ctx.send(f"❌ Invalid `last` parameter, format must be `?d?h?m?s`.")
                date2 = datetime.now(timezone.utc)
                date1 = datetime.now(timezone.utc) - input_time
            else:
                date1 = param["after"] or datetime(2021,7,7,14,15,10)
                date2 = param["before"] or datetime.now(timezone.utc)
        else:
            date1 = datetime.now(timezone.utc)
            date2 = datetime.now(timezone.utc)

        # check on lines arg
        nb_line = int(nb_line)
        if nb_line > 40:
            return await ctx.send("❌ Can't show more than 40 lines.")

        # check on sort arg
        if not sort_opt:
            sort = 'canvas' if canvas_opt else 'alltime'
        else:
            sort = sort_opt

        # fetch the leaderboard from the database
        ldb = get_pixels_placed_between(date1,date2,canvas_opt,sort,username)
        date = ldb[0][4]

        # trim the leaderboard to only get the lines asked
        if username:
            # looking for the index and pixel count of the given user
            name_index = None
            for index,line in enumerate(ldb):
                name = list(line)[1]
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
        if username:
            column_names.append("Diff")
        if speed_opt:
            column_names.append("Speed")

        # build the content of the leaderboard
        res_ldb = []
        for i in range(len(ldb)):
            res_ldb.append(list(ldb[i][0:3]))
            if ldb[i][2] != None:
                res_ldb[i][2] = f'{int(res_ldb[i][2]):,}'.replace(","," ")
            else:
                res_ldb[i][2] = "???"
            if username:
                # add the diff values
                diff = user_pixels-ldb[i][2]
                diff = f'{int(diff):,}'.replace(","," ") # convert to string
                res_ldb[i].append(diff)

            if speed_opt:
                diff_pixels = ldb[i][3]
                diff_time = ldb[i][6] - ldb[i][5]
                nb_hours = diff_time/timedelta(hours=1)
                speed = diff_pixels/nb_hours
                res_ldb[i].append(f'{round(speed,1)} px/h')

        # format the leaderboard to be printed
        text = ""
        if speed_opt:
            past_time = round_minutes(ldb[0][5])
            recent_time = round_minutes(ldb[0][6])
            text += "\nSpeed between `{}` and `{}` ({})\n".format(
                format_datetime(past_time),
                format_datetime(recent_time),
                td_format(recent_time-past_time)
            )

        if sort_opt != None:
            text += "Sorted by: `{}`\n".format(sort)

        text += "```diff\n"
        text += self.format_leaderboard(res_ldb,column_names,username[0] if username else None)
        text += "```"

        # create a discord embed with the leaderboard and send it
        if canvas_opt:
            emb = discord.Embed(title="Canvas Leaderboard",description=text)
        else:
            emb = discord.Embed(title="All-time Leaderboard",description=text)

        footer_text = "Last updated: {} ({} ago).".format(
            format_datetime(date),
            td_format(datetime.utcnow()-date)
            )

        emb.set_footer(text=footer_text)
        await ctx.send(embed=emb)

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

    @staticmethod
    def format_leaderboard(table,column_names,name=None):
        ''' Format the leaderboard in a string to be printed '''
        if not table:
            return
        if len(table[0]) != len(column_names):
            raise ValueError("The number of column in table and column_names don't match.")

        # find the longest columns
        table.insert(0,column_names)
        longest_cols = [
            (max([len(str(row[i])) for row in table]) + 1)
            for i in range(len(table[0]))]

        # format the header
        LINE = "-"*(sum(longest_cols) + len(table[0]*2))
        row_format = "|".join([" {:<" + str(longest_col) + "}" for longest_col in longest_cols])
        str_table = f'{LINE}\n {row_format.format(*table[0])}\n{LINE}\n'

        # format the body
        for row in table[1:]:
            str_table += ("+" if row[1] == name else " ") + row_format.format(*row) + "\n"

        return str_table

def setup(client):
    client.add_cog(PxlsLeaderboard(client))