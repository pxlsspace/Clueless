import plotly.graph_objects as go
import discord
from datetime import datetime, timedelta,timezone
from discord.ext import commands
from itertools import cycle

from utils.discord_utils import image_to_file, format_number
from utils.setup import db_stats_manager as db_stats
from utils.arguments_parser import parse_speed_args
from utils.table_to_image import table_to_image
from utils.time_converter import format_datetime, round_minutes_down, str_to_td
from utils.plot_utils import layout, BACKGROUND_COLOR, COLORS, fig2img
from utils.image_utils import v_concatenate

class PxlsSpeed(commands.Cog):

    def __init__(self,client):
        self.client = client

    @commands.command(usage="<name> [-canvas] [-groupby [day|hour]] [-progress] [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]",
    description = "Show the speed of a pxls user with a graph.",
    help = """- `<names>`: list of pxls users names separated by a space
              - `[-canvas|-c]`: show the canvas stats
              - `[-groupby|-g]`: show a bar chart for each `day` or `hour`
              - `[-progress|-p]`: compare the progress between users
              - `[-last <?d?h?m?s>]`: get the speed in the last x hours/days/minutes/seconds (default: 1 day)
              - `[-before <date time>]`: show the speed before a date and time (format YYYY-mm-dd HH:MM)
              - `[-after <date time>]`: show the speed after a date and time (format YYYY-mm-dd HH:MM)"""
    )
    async def speed(self,ctx,*args):
        ''' Show the average speed of a user in the last x min, hours or days '''
        try:
            param = parse_speed_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        # check on date arguments
        if param["before"] == None and param["after"] == None:
            date = param["last"]
            input_time = str_to_td(date)
            if not input_time:
                return await ctx.send(f"❌ Invalid `last` parameter, format must be `{ctx.prefix}{ctx.command.name}{ctx.command.usage}`.")
            recent_time = datetime.now(timezone.utc)
            old_time = round_minutes_down(datetime.now(timezone.utc) - input_time)
        else:
            old_time = param["after"] or datetime(1900,1,1,0,0,0)
            recent_time = param["before"] or datetime.now(timezone.utc)

        names = param["names"]
        canvas_opt = param["canvas"]
        groupby_opt = param["groupby"]

        # get the data we need
        full_ldb = await db_stats.get_pixels_placed_between(old_time,recent_time,canvas_opt,'speed')
        ldb = []
        for user in full_ldb:
            if user[1] in names:
                ldb.append(user)
        #check if any user was found
        if not ldb:
            return await ctx.send("❌ User(s) not found.")

        now_time = ldb[0][6]
        past_time = ldb[0][5]

        # Select the data we need to display:
        #  name, current pixels, placed in the time frame, speed in px/h, px/d
        res = []
        for user in ldb:
            name = user[1]
            pixels = user[2]
            if pixels == None:
                continue
            pixels = format_number(pixels)
            diff_pixels = user[3]
            diff_time = user[6] - user[5]
            nb_hours = diff_time/timedelta(hours=1)
            speed_px_h = diff_pixels/nb_hours
            speed_px_d = speed_px_h*24
            res.append([name,pixels,format_number(diff_pixels),round(speed_px_h),round(speed_px_d)])

        if len(res) == 0:
            return await ctx.send("❌ User(s) not found (try adding `-c` in the command).")
        # create the headers needed for the table
        alignments = ["left","right","right","right","right"]
        titles = ["Name","Pixels","Placed","px/h","px/d"]
        table_colors = cycle_through_list(COLORS,len(res))
        # get the image of the table
        table_image = table_to_image(res,titles,alignments,table_colors)

        # create the graph
        user_list = [user[1] for user in ldb]
        if groupby_opt:
            graph = await get_grouped_graph(user_list,past_time,now_time,groupby_opt)
        else:
            graph = await get_stats_graph(user_list,canvas_opt,past_time,now_time,param["progress"])
        graph_image = fig2img(graph)

        # merge the table image and graph image
        res_image = v_concatenate(table_image,graph_image,gap_height=20)

        # create the embed
        description = f"Between {format_datetime(past_time)} and {format_datetime(now_time)}"
        emb = discord.Embed(color=0x66c5cc)
        emb.add_field(name='Speed',value = description)

        # send the embed with the graph image
        file = image_to_file(res_image,"speed.png",emb)
        await ctx.send(file=file,embed=emb)

def setup(client):
    client.add_cog(PxlsSpeed(client))

async def get_stats_graph(user_list,canvas,date1,date2=datetime.now(timezone.utc),progress_opt=False):

    # create the graph
    fig = go.Figure(layout=layout)
    fig.update_layout(showlegend=False)
    fig.update_layout(title=f"<span style='color:{COLORS[0]};'>Speed</span>")

    for i,user in enumerate(user_list):
        # get the data
        stats = await db_stats.get_stats_history(user,date1,date2)
        if not stats:
            continue

        dates = [stat[3] for stat in stats]
        if canvas:
            pixels = [stat[2] for stat in stats]
        else:
            pixels = [stat[1] for stat in stats]
        
        if progress_opt:
            pixels = [pixel - pixels[0] for pixel in pixels]

        # trace the user data
        fig.add_trace(go.Scatter(
            x=dates,
            y=pixels,
            mode='lines',
            name=user,
            line=dict(width=4),
            marker=dict(color= COLORS[i%len(COLORS)],size=6)
            )
        )

        # add a marge at the right to add the name
        longest_name = max([len(user) for user in user_list])
        fig.update_layout(margin=dict(r=(longest_name+2)*26))

        # add the name
        fig.add_annotation(
            xanchor='left',
            xref="paper",
            yref="y",
            x = 1.01,
            y = pixels[-1],
            text = ("<b>%s</b>" % user),
            showarrow = False,
            font = dict(color= COLORS[i%len(COLORS)],size=40)
        )
    return fig

async def get_grouped_graph(user_list,date1,date2,groupby_opt):

    # check on the groupby param
    if not groupby_opt in ["day","hour"]:
        raise ValueError("'groupby' parameter can only be 'day' or 'hour'.")

    # create the graph and style
    fig = go.Figure(layout=layout)
    fig.update_yaxes(rangemode='tozero')

    # the title displays the user if there is only 1 in the user_list
    fig.update_layout(title="<span style='color:{};'>Speed per {}{}</span>".format(
        COLORS[0],
        groupby_opt,
        f" for <b>{user_list[0]}</b>" if len(user_list) == 1 else ""
    ))


    for i,user in enumerate(user_list):
        # get the data
        stats = await db_stats.get_grouped_stats_history(user,date1,date2,groupby_opt)
        stats = stats[1:]
        if not stats:
            continue

        if groupby_opt == "day":
            dates = [stat[4][:10] for stat in stats]
        elif groupby_opt == "hour":
            dates = [stat[4][:13] for stat in stats]
        pixels = [stat[3] for stat in stats]

        # trace the user data
        fig.add_trace(
            go.Bar(
                name='<span style="color:{};font-size:40;"><b>{}</b></span>'.format(COLORS[i%len(COLORS)], user),
                x = dates,
                y = pixels,
                # add an outline of the bg color to the text
                text = ['<span style = "text-shadow:\
                     -{2}px -{2}px 0 {0},\
                     {2}px -{2}px 0 {0},\
                     -{2}px {2}px 0 {0},\
                     {2}px {2}px 0 {0},\
                     0px {2}px 0px {0},\
                     {2}px 0px 0px {0},\
                     -{2}px 0px 0px {0},\
                     0px -{2}px 0px {0};">{1}</span>'.format(BACKGROUND_COLOR,pixel,2) for pixel in pixels],
                textposition = 'outside',
                marker = dict(color=COLORS[i%len(COLORS)], opacity=0.95),
                textfont = dict(color=COLORS[i%len(COLORS)], size=40),
                cliponaxis = False
            )
        )
    return fig

def cycle_through_list(list,number_of_element:int):
    ''' loop through a list the desired amount of time
    example: cycle_through_list([1,2,3],6) -> [1,2,3,1,2,3] '''
    if len(list) == 0 or number_of_element == 0:
        return None
    list = cycle(list)
    res = []
    count = 0
    for i in list:
        res.append(i)
        count += 1
        if count == number_of_element:
            break
    return res
