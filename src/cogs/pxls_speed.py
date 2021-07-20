import plotly.graph_objects as go
import plotly.express as px

from io import BytesIO
from PIL import Image
from datetime import datetime, timedelta,timezone
from discord.ext import commands
import discord

from utils.discord_utils import image_to_file, format_number, format_table
from utils.database import sql_select, get_pixels_placed_between
from utils.arguments_parser import parse_speed_args
from utils.time_converter import format_datetime, round_minutes_down, str_to_td

BACKGROUND_COLOR = "#202225"
GRID_COLOR = "#b9bbbe"
class PxlsSpeed(commands.Cog):

    def __init__(self,client):
        self.client = client

    @commands.command(usage="<name> [-canvas|-c] [-groupby|-g [day|hour]] [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]",
    description = "Show the average speed of a pxls user.",
    help = """- `<names>`: list of pxls users names separated by a space
              - `[-canvas|-c]`: to show canvas stats
              - `[-groupby|-g]`: show a bar chart for each `day` or `hour`
              - `[-last <?d?h?m?s>]`: get the average speed in the last x hours/days/minutes/seconds (default: 1 day)
              - `[-before <date time>]`: to show the average speed before a date and time (format YYYY-mm-dd HH:MM)
              - `[-after <date time>]`: to show the average speed after a date and time (format YYYY-mm-dd HH:MM)"""
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

        ldb = get_pixels_placed_between(old_time,recent_time,canvas_opt,'speed',names)
        if not ldb:
            return await ctx.send("❌ User(s) not found.")
        now_time = ldb[0][6]
        past_time = ldb[0][5]
        res = []
        for user in ldb:
            name = user[1]
            pixels = format_number(user[2])
            diff_pixels = user[3]
            diff_time = user[6] - user[5]
            nb_hours = diff_time/timedelta(hours=1)
            speed_px_h = diff_pixels/nb_hours
            speed_px_d = speed_px_h*24
            res.append([name,pixels,format_number(diff_pixels),round(speed_px_h),round(speed_px_d)])

        speed_px_d = round(speed_px_h*24,1)
        speed_px_h = round(speed_px_h,1)

        res_formated = format_table(res,["Name","Pixels","Placed","px/h","px/d"],["<",">",">",">",">"])

        # create the embed
        title = f"Speed between {format_datetime(past_time)} and {format_datetime(now_time)}"
        emb = discord.Embed(color=0x66c5cc)
        emb.add_field(name=title,value= "```\n" + res_formated + "```")

        # create the graph
        if groupby_opt:
            graph = get_grouped_graph(names,past_time,now_time,groupby_opt)

        else:
            graph = get_stats_graph(names,canvas_opt,past_time,now_time)
        img = fig2img(graph)

        # send the embed with the graph image
        file = image_to_file(img,"statsgraph.png",emb)
        await ctx.send(file=file,embed=emb)

def setup(client):
    client.add_cog(PxlsSpeed(client))

def fig2img(fig):
    buf = BytesIO()
    fig.write_image(buf,format="png",width=2000,height=900,scale=1)
    img = Image.open(buf)
    return img

layout = go.Layout(
    paper_bgcolor=BACKGROUND_COLOR,
    plot_bgcolor=BACKGROUND_COLOR,
    font_color=GRID_COLOR,
    font_size=35,
    yaxis = dict(showgrid=True, gridwidth=1, gridcolor=GRID_COLOR,tickformat=',d'),
    xaxis = dict(showgrid=True, gridwidth=1, gridcolor=GRID_COLOR)
)

def get_stats_graph(user_list,canvas,date1,date2=datetime.now(timezone.utc)):

    # create the graph
    fig = go.Figure(layout=layout)
    fig.update_layout(showlegend=False)
    colors = px.colors.qualitative.Pastel
    for i,user in enumerate(user_list):
        # get the data
        stats = sql_select("""SELECT * FROM pxls_user_stats
                            WHERE name = ?
                            AND date >= ?
                            AND date <= ?""",(user,date1,date2))
        if not stats:
            continue

        dates = [stat[3] for stat in stats]
        if canvas:
            pixels = [stat[2] for stat in stats]
        else:
            pixels = [stat[1] for stat in stats]

        # trace the user data
        fig.add_trace(go.Scatter(
            x=dates,
            y=pixels,
            mode='lines',
            name=user,
            line=dict(width=4),
            marker=dict(color= colors[i%len(colors)],size=6)
            )
        )

        # add a marge at the right to add the name
        longest_name = max([len(user) for user in user_list])
        fig.update_layout(margin=dict(r=(longest_name+1)*26))

        # add the name
        fig.add_annotation(
            xanchor='left',
            xref="paper",
            yref="y",
            x = 1.01,
            y = pixels[-1],
            text = ("<b>%s</b>" % user),
            showarrow = False,
            font = dict(color= colors[i%len(colors)],size=40)
        )
    return fig

def get_grouped_graph(user_list,date1,date2,groupby_opt):

    # check on the groupby param
    if groupby_opt == "day":
        groupby = '%Y-%m-%d'
    elif groupby_opt == "hour":
        groupby = '%Y-%m-%d %H'
    else:
        raise ValueError("'groupby' parameter can only be 'day' or 'hour'.")

    # create the graph and style
    fig = go.Figure(layout=layout)
    fig.update_yaxes(rangemode='tozero')
    colors = px.colors.qualitative.Pastel

    for i,user in enumerate(user_list):
        # get the data
        stats = sql_select(
            """SELECT name, alltime_count, canvas_count,
                    alltime_count-(LAG(alltime_count) OVER (ORDER BY date)) as placed,
                    MAX(date) as last_datetime
                FROM pxls_user_stats
                WHERE name = ?
                AND DATE >= ?
                AND DATE <= ?
                GROUP BY strftime(?,date)
                """,
            (user,date1,date2,groupby))
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
                name='<span style="color:{};font-size:40;"><b>{}</b></span>'.format(colors[i%len(colors)], user),
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
                marker = dict(color=colors[i%len(colors)], opacity=0.95),
                textfont = dict(color=colors[i%len(colors)], size=40),
                cliponaxis = False
            )
        )
    return fig
