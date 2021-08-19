import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import plotly.graph_objects as go
from utils.image_utils import hex_str_to_int

from utils.setup import db_stats_manager as db_stats, db_users_manager as db_users
from utils.time_converter import *
from utils.arguments_parser import parse_leaderboard_args
from utils.discord_utils import format_number, image_to_file
from utils.table_to_image import table_to_image
from utils.plot_utils import fig2img, get_theme, hex_to_rgba_string
from utils.cooldown import get_best_possible

class PxlsLeaderboard(commands.Cog, name="Pxls Leaderboard"):

    def __init__(self, client):
        self.client = client

    ### Discord commands ###

    # TODO: error when the time frame is before the canvas start
    # or automatically get alltime values
    @commands.command(
        usage = "[username] [-canvas] [-lines <number>] [-graph] [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]",
        description = "Show the all-time or canvas leaderboard.",
        aliases=["ldb"],
        help = """- `[username]`: center the leaderboard on this user
                  - `[-canvas|-c]`: to get the canvas leaderboard
                  - `[[-lines|-l] <number>]`: number of lines to show, must be less than 40 (default 20)
                  - `[-graph|-g]`: show a bar graph of the leaderboard
                  - `[-last ?d?h?m?s]`: show the leaderboard of the last ? day, ? hour, ? min, ? second"""
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
        last_opt = param["last"]
        graph_opt = param["graph"]

        # get the user theme
        discord_user = await db_users.get_discord_user(ctx.author.id)
        current_user_theme = discord_user["color"] or "default"
        theme = get_theme(current_user_theme)

        # if a time value is given, we will show the leaderboard during this time
        if param["before"] or param["after"] or last_opt:
            speed_opt = True
            sort_opt = "speed"
            if param["before"] == None and param["after"] == None:
                date = last_opt
                input_time = str_to_td(date)
                if not input_time:
                    return await ctx.send(f"❌ Invalid `last` parameter, format must be `?d?h?m?s`.")
                date2 = datetime.now(timezone.utc)
                date1 = round_minutes_down(datetime.now(timezone.utc) - input_time)
            else:
                last_opt = None
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
            #canvas_opt = "canvas" # only get the canvas stats when sorting by speed

        # fetch the leaderboard from the database
        async with ctx.typing():
            last_date, datetime1, datetime2, ldb = await db_stats.get_pixels_placed_between(date1,date2,canvas_opt,sort)

        # check that we can actually calculate the speed
        if speed_opt and datetime1 == datetime2:
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
            res_ldb.append([])
            # add the rank
            rank = ldb[i][0]
            if rank > 1000:
                rank = ">1000"
            res_ldb[i].append(rank)

            # add the name
            res_ldb[i].append(ldb[i][1])

            # add the pixel count
            if speed_opt:
                res_ldb[i].append(ldb[i][3])
            else:
                res_ldb[i].append(ldb[i][2])
            # format the number
            if res_ldb[i][2] != None:
                res_ldb[i][2] = format_number(res_ldb[i][2])
            else:
                res_ldb[i][2] = "???"

            # add the diff values
            if username:
                try:
                    if speed_opt:
                        diff = user_pixels-ldb[i][3]
                    else:
                        diff = user_pixels-ldb[i][2]
                    diff = f'{int(diff):,}'.replace(","," ") # convert to string
                    res_ldb[i].append(diff)
                except:
                    res_ldb[i].append("???")

            # add the speed
            if speed_opt:
                diff_pixels = ldb[i][3] or 0
                diff_time = (datetime2 - datetime1)
                nb_hours = diff_time/timedelta(hours=1)
                speed = diff_pixels/nb_hours
                # show the speed in pixel/day if the time frame is more than a day
                if nb_hours > 24:
                    speed = speed*24
                    res_ldb[i].append(f'{round(speed,1)} px/d')
                else:
                    res_ldb[i].append(f'{round(speed,1)} px/h')

        # create the image with the leaderboard data
        colors = None
        if username:
            colors = []
            for e in res_ldb:
                if e[1] == username[0]:
                    colors.append(theme.get_palette(1)[0])
                else:
                    colors.append(None)
        img = await self.client.loop.run_in_executor(
            None,table_to_image,res_ldb,column_names,alignments2,colors,theme)

        # make title and embed header
        text = ""
        if speed_opt:
            past_time = datetime1
            recent_time = datetime2
            diff_time = round_minutes_down(recent_time)-round_minutes_down(past_time)
            diff_time_str = td_format(diff_time)
            if last_opt:
                title = "Leaderboard of the last {}".format(
                    diff_time_str[2:] if (diff_time_str.startswith("1 ") and not ',' in diff_time_str)
                    else diff_time_str)
            else:
                title = "Leaderboard"
                text += "• Between {} and {}\n({})\n".format(
                    format_datetime(past_time),
                    format_datetime(recent_time),
                    td_format(diff_time)
                )
            # calculate the best possbile amount in the time frame
            best_possible,average_cooldown = await get_best_possible(datetime1,datetime2)
            text += f"• Average cooldown: `{round(average_cooldown,2)}` seconds\n"
            text += f"• Best possible (without stack): ~`{format_number(best_possible)}` pixels.\n"

        elif canvas_opt:
            title = "Canvas Leaderboard"
        else:
            title = "All-time Leaderboard"

        if not(param["before"] or param["after"]):
            text +=  f"• Last updated: {format_datetime(last_date,'R')}"
    
        # make the bars graph
        if graph_opt:
            data = [int(user[2].replace(" ","")) if user[2] != "???" else None for user in res_ldb]
            theme_colors = theme.get_palette(1)
            if username:
                names = [(f"<span style='color:{theme_colors[0]};'>{user[1]}</span>" if user[1] == username[0] else user[1]) for user in res_ldb]
                colors = [(theme_colors[0] if user[1] == username[0] else theme.off_color) for user in res_ldb]
            else:
                names = [user[1] for user in res_ldb]
                colors = [theme_colors[0]]*len(res_ldb)
            fig = self.make_bars(names,data,title,theme,colors)

            bars_img = fig2img(fig)
            bars_file = image_to_file(bars_img,"bar_chart.png")

        # create a discord embed
        emb = discord.Embed(color=hex_str_to_int(theme.get_palette(1)[0]),
            title=title,description=text)
        file = image_to_file(img,"leaderboard.png",emb)

        # send graph and embed
        await ctx.send(embed=emb,file=file)
        if graph_opt:
            await ctx.send(file=bars_file)

    @staticmethod
    def make_bars(users,pixels,title,theme,colors=None):
        if colors == None:
            colors = theme.get_palette(len(users))
        # create the graph and style
        fig = go.Figure(layout=theme.get_layout(with_annotation=False))
        fig.update_yaxes(rangemode='tozero')
        fig.update_xaxes(tickmode='linear')
        fig.update_layout(annotations=[])
        fig.update()
        # the title displays the user if there is only 1 in the user_list
        fig.update_layout(title="<span style='color:{};'>{}</span>".format(
            theme.get_palette(1)[0],
            title))

        text = ['<span style = "text-shadow:\
                        -{2}px -{2}px 0 {0},\
                        {2}px -{2}px 0 {0},\
                        -{2}px {2}px 0 {0},\
                        {2}px {2}px 0 {0},\
                        0px {2}px 0px {0},\
                        {2}px 0px 0px {0},\
                        -{2}px 0px 0px {0},\
                        0px -{2}px 0px {0};">{1}</span>'.format(theme.background_color,pixel,2) for pixel in pixels]

        # trace the user data
        if theme.has_underglow == True:
            # different style if the theme has underglow
            fig.add_trace(
                go.Bar(
                    x = users,
                    y = pixels,
                    text = text,
                    textposition = 'outside',
                    marker_color = [hex_to_rgba_string(color,0.3) for color in colors],
                    marker_line_color = colors,
                    marker_line_width=2.5,
                    textfont = dict(color=colors, size=40),
                    cliponaxis = False
                )
            )
        else:
            fig.add_trace(
                go.Bar(
                    x = users,
                    y = pixels,
                    # add an outline of the bg color to the text
                    text = text,
                    textposition = 'outside',
                    marker = dict(color=colors, opacity=0.95),
                    textfont = dict(color=colors, size=40),
                    cliponaxis = False
                )
            )
        return fig

def setup(client):
    client.add_cog(PxlsLeaderboard(client))