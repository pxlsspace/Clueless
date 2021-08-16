import plotly.graph_objects as go
import discord
from datetime import datetime, timedelta,timezone
from discord.ext import commands
from itertools import cycle

from utils.discord_utils import image_to_file, format_number
from utils.setup import db_stats_manager as db_stats, db_users_manager as db_users
from utils.arguments_parser import parse_speed_args
from utils.table_to_image import table_to_image
from utils.time_converter import format_datetime, round_minutes_down, str_to_td
from utils.plot_utils import add_glow, get_theme,fig2img, hex_to_rgba_string
from utils.image_utils import hex_str_to_int, v_concatenate
from utils.cooldown import get_best_possible

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

        # get the user theme
        discord_user = await db_users.get_discord_user(ctx.author.id)
        current_user_theme = discord_user["color"] or "default"
        theme = get_theme(current_user_theme)

        # check on name arguments
        names = param["names"]
        if len(names) == 0:
            pxls_user_id = discord_user["pxls_user_id"]
            if pxls_user_id == None:
                return await ctx.send(f"❌ You need to specify at least one username.\n\(You can also set a default username with `{ctx.prefix}setname <username>`)")
            else:
                name = await db_users.get_pxls_user_name(pxls_user_id)
                names.append(name)

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

        canvas_opt = param["canvas"]
        groupby_opt = param["groupby"]

        # get the data we need
        last_time, past_time, now_time, full_ldb = await db_stats.get_pixels_placed_between(old_time,recent_time,canvas_opt,'speed')
        
        # check that we can calculate a speed
        if past_time == now_time:
            return await ctx.send("❌ The time frame given is too short.")

        ldb = []
        for user in full_ldb:
            if user[1] in names:
                ldb.append(user)
        #check if any user was found
        if not ldb:
            return await ctx.send("❌ User(s) not found.")

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
            diff_time = now_time - past_time
            nb_hours = diff_time/timedelta(hours=1)
            speed_px_h = diff_pixels/nb_hours
            speed_px_d = speed_px_h*24
            res.append([name,pixels,format_number(diff_pixels),round(speed_px_h),round(speed_px_d)])

        if len(res) == 0:
            return await ctx.send("❌ User(s) not found (try adding `-c` in the command).")
        # create the headers needed for the table
        alignments = ["left","right","right","right","right"]
        titles = ["Name","Pixels","Placed","px/h","px/d"]
        table_colors = theme.get_palette(len(res))
        # get the image of the table
        table_image = table_to_image(res,titles,alignments,table_colors,theme=theme)

        # create the graph
        user_list = [user[1] for user in ldb]
        if groupby_opt:
            graph = await get_grouped_graph(user_list,past_time,now_time,groupby_opt,canvas_opt,theme)
        else:
            graph = await get_stats_graph(user_list,canvas_opt,past_time,now_time,param["progress"],theme)
        graph_image = fig2img(graph)

        # merge the table image and graph image
        res_image = v_concatenate(table_image,graph_image,gap_height=20)

        # calculate the best possbile amount in the time frame
        best_possible,average_cooldown = await get_best_possible(past_time,now_time)

        # create the embed
        description = f"• Between {format_datetime(past_time)} and {format_datetime(now_time)}\n"
        description += f"• Average cooldown: `{round(average_cooldown,2)}` seconds\n"
        description += f"• Best possible (without stack): ~`{best_possible}` pixels."
        emb = discord.Embed(color=hex_str_to_int(theme.get_palette(1)[0]))
        emb.add_field(name='Speed',value = description)

        # send the embed with the graph image
        file = image_to_file(res_image,"speed.png",emb)
        await ctx.send(file=file,embed=emb)

def setup(client):
    client.add_cog(PxlsSpeed(client))

async def get_stats_graph(user_list,canvas,date1,date2,progress_opt,theme):

    # create the graph
    colors = theme.get_palette(len(user_list))
    fig = go.Figure(layout=theme.get_layout())
    fig.update_layout(showlegend=False)
    fig.update_layout(title=f"<span style='color:{colors[0]};'>Speed</span>")

    for i,user in enumerate(user_list):
        # get the data
        stats = await db_stats.get_stats_history(user,date1,date2,canvas)
        if not stats:
            continue
        dates = [stat["datetime"] for stat in stats]
        if canvas:
            pixels = [stat["canvas_count"] for stat in stats]
        else:
            pixels = [stat["alltime_count"] for stat in stats]

        if progress_opt:
            if not pixels[0]:
                # ignore the user if it has None pixels
                # (happens when canvas_opt is False and the user doesn't have enough pixels 
                # to be on the alltime leaderboard)
                continue
            pixels = [pixel - pixels[0] for pixel in pixels]

        # trace the user data
        if theme.has_underglow == True and min(pixels) ==0:
            fig.add_trace(go.Scatter(
                x=dates,
                y=pixels,
                mode='lines',
                name=user,
                line=dict(width=4),
                marker=dict(color= colors[i],size=6),
                fill = 'tozeroy',
                fillcolor=hex_to_rgba_string(colors[i],0.04)
                )
            )

        else:
            fig.add_trace(go.Scatter(
                x=dates,
                y=pixels,
                mode='lines',
                name=user,
                line=dict(width=4),
                marker=dict(color= colors[i],size=6)
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
            font = dict(color= colors[i],size=40)
        )

    if theme.has_glow == True:
        add_glow(fig,nb_glow_lines=5, alpha_lines=0.5, diff_linewidth=4)
    return fig

async def get_grouped_graph(user_list,date1,date2,groupby_opt,canvas_opt,theme):

    # check on the groupby param
    if not groupby_opt in ["day","hour"]:
        raise ValueError("'groupby' parameter can only be 'day' or 'hour'.")

    # create the graph and style
    colors = theme.get_palette(len(user_list))
    fig = go.Figure(layout=theme.get_layout())
    fig.update_yaxes(rangemode='tozero')

    # the title displays the user if there is only 1 in the user_list
    fig.update_layout(title="<span style='color:{};'>Speed per {}{}</span>".format(
        colors[0],
        groupby_opt,
        f" for <b>{user_list[0]}</b>" if len(user_list) == 1 else ""
    ))


    for i,user in enumerate(user_list):
        # get the data
        stats = await db_stats.get_grouped_stats_history(user,date1,date2,groupby_opt,canvas_opt)
        stats = stats[1:]
        if not stats:
            continue

        if groupby_opt == "day":
            dates = [stat["last_datetime"][:10] for stat in stats]
        elif groupby_opt == "hour":
            dates = [stat["last_datetime"][:13] for stat in stats]
        pixels = [stat["placed"] for stat in stats]

        # add an outline of the bg color to the text above the bars
        text = ['<span style = "text-shadow:\
        -{2}px -{2}px 0 {0},\
        {2}px -{2}px 0 {0},\
        -{2}px {2}px 0 {0},\
        {2}px {2}px 0 {0},\
        0px {2}px 0px {0},\
        {2}px 0px 0px {0},\
        -{2}px 0px 0px {0},\
        0px -{2}px 0px {0};">{1}</span>'.format(theme.background_color,pixel,2) for pixel in pixels]

        name='<span style="color:{};font-size:40;"><b>{}</b></span>'.format(colors[i], user)
        # trace the user data
        if theme.has_underglow == True:
            # different style if the theme has underglow
            fig.add_trace(
                go.Bar(
                    name=name,
                    x = dates,
                    y = pixels,
                    text = text,
                    textposition = 'outside',
                    marker_color = hex_to_rgba_string(colors[i],0.15),
                    marker_line_color =colors[i],
                    marker_line_width=2.5,
                    textfont = dict(color=colors[i], size=40),
                    cliponaxis = False
                )
            )
        else:
            fig.add_trace(
                go.Bar(
                    name=name,
                    x = dates,
                    y = pixels,
                    text = text,
                    textposition = 'outside',
                    marker = dict(color=colors[i], opacity=0.9),
                    textfont = dict(color=colors[i], size=40),
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
