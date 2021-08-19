import plotly.graph_objects as go
import discord
from datetime import datetime, timedelta,timezone
from discord.ext import commands
from itertools import cycle

from utils.discord_utils import image_to_file, format_number
from utils.setup import db_stats_manager as db_stats, db_users_manager as db_users
from utils.arguments_parser import parse_speed_args
from utils.table_to_image import table_to_image
from utils.time_converter import format_datetime, round_minutes_down, str_to_td, td_format
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

        # select the discord user's pxls username if it has one linked
        names = param["names"]
        if len(names) == 0:
            pxls_user_id = discord_user["pxls_user_id"]
            if pxls_user_id == None:
                return await ctx.send(f"❌ You need to specify at least one username.\n\(You can also set a default username with `{ctx.prefix}setname <username>`)")
            else:
                name = await db_users.get_pxls_user_name(pxls_user_id)
                names.append(name)

        # check on date arguments
        canvas_opt = param["canvas"]
        groupby_opt = param["groupby"]
        if param["before"] == None and param["after"] == None:
            # if no date argument and -canvas : show the whole canvas
            if param["last"] == None and canvas_opt == True:
                old_time = datetime(1900,1,1,0,0,0)
                recent_time = datetime.now(timezone.utc)
            else:
                date = param["last"] or "1d"
                input_time = str_to_td(date)
                if not input_time:
                    return await ctx.send(f"❌ Invalid `last` parameter, format must be `?d?h?m?s`.")
                recent_time = datetime.now(timezone.utc)
                old_time = round_minutes_down(datetime.now(timezone.utc) - input_time)
        else:
            old_time = param["after"] or datetime(1900,1,1,0,0,0)
            recent_time = param["before"] or datetime.now(timezone.utc)

        async with ctx.typing():
            # get the data we need
            if groupby_opt:
                (past_time, now_time, stats) = await db_stats.get_grouped_stats_history(
                    names, old_time, recent_time,groupby_opt,canvas_opt)
            else:
                (past_time, now_time, stats) = await db_stats.get_stats_history(
                    names, old_time,recent_time,canvas_opt)

            # check that we can calculate the speed
            if past_time == now_time:
                return await ctx.send("❌ The time frame given is too short.")
            diff_time = now_time - past_time
            nb_hour = diff_time/timedelta(hours=1)

            # format the data to be displayed
            formatted_data = []
            found_but_no_data = False
            for user in stats:
                data = user[1]
                if groupby_opt:
                    # truncate the first data if we're groupping by day/hour
                    data = data[1:]

                if len(data) == 0:
                    continue

                # last username
                name = data[-1]["name"]
                # current pixels
                current_pixels = data[-1]["pixels"]

                if groupby_opt:
                    if all([d["placed"]==None for d in data]):
                        # skip the user if all the values are None
                        continue
                    diff_pixels = sum([(d["placed"] or 0) for d in data])
                else:
                    # find first non-null value
                    lowest_pixels = None
                    for d in data:
                        if d["pixels"] != None:
                            lowest_pixels = d["pixels"]
                            break
                    if lowest_pixels == None or current_pixels == None:
                        # the user exists in the database but doesnt have data
                        # in the given time frame
                        found_but_no_data = True
                        continue
                    diff_pixels = current_pixels - lowest_pixels

                # calculate the speed
                speed_px_h = diff_pixels/nb_hour
                speed_px_d = speed_px_h*24

                # format data for the graph
                if groupby_opt:
                    if groupby_opt == "day":
                        dates = [stat["first_datetime"][:10] for stat in data]
                    elif groupby_opt == "hour":
                        dates = [stat["first_datetime"][:13] for stat in data]
                    pixels = [stat["placed"] for stat in data]
                
                else:
                    dates = [stat["datetime"] for stat in data]
                    if param["progress"]:
                        # substract the first value to each value so they start at 0
                        pixels = [stat["pixels"] - data[0]["pixels"] for stat in data]
                    else:
                        pixels = [stat["pixels"] for stat in data]

                formatted_data.append([
                    name,
                    current_pixels,
                    diff_pixels,
                    speed_px_h,
                    speed_px_d,
                    dates,
                    pixels
                ])

            if len(formatted_data) == 0:
                msg = "❌ User{} not found{}.".format(
                    's' if len(names) >1 else '',
                    " (try adding `-c` in the command)" if found_but_no_data else ''
                    )
                return await ctx.send(msg)

            # sort the data by the 3rd column (progress in the time frame)
            formatted_data.sort(key = lambda x:x[2],reverse=True)

            # create the headers needed for the table
            alignments = ["center","right","right","right","right"]
            titles = ["Name","Pixels","Progress","px/h","px/d"]
            table_colors = theme.get_palette(len(formatted_data))

            # make the title
            if groupby_opt:
                title="Speed {}".format(
                    "per " + groupby_opt if groupby_opt else "")
                title += f" for {formatted_data[0][0]}" if len(formatted_data) == 1 else ""
            elif canvas_opt and param["last"] == None:
                title = "Canvas Speed"
            else:
                title = "Speed"

            
            # get the image of the table
            table_data = [d[:-2] for d in formatted_data]
            table_data = [[format_number(c) for c in row] for row in table_data]
            table_image = table_to_image(table_data,titles,
            alignments,table_colors,theme=theme)

            # create the graph
            graph_data = [[d[0],d[5],d[6]] for d in formatted_data]
            if groupby_opt:
                graph_image = await self.client.loop.run_in_executor(None,
                    get_grouped_graph,graph_data,groupby_opt,title,theme)
            else:
                graph_image = await self.client.loop.run_in_executor(None,
                    get_stats_graph,graph_data,title,theme)

            # merge the table image and graph image
            res_image = v_concatenate(table_image,graph_image,gap_height=20)

            # calculate the best possbile amount in the time frame
            best_possible,average_cooldown = await get_best_possible(past_time,now_time)

            # create the embed
            description = f"• Between {format_datetime(past_time)} and {format_datetime(now_time)}\n"
            description += f"• Average cooldown: `{round(average_cooldown,2)}` seconds\n"
            description += f"• Best possible (without stack): ~`{format_number(best_possible)}` pixels."
            emb = discord.Embed(color=hex_str_to_int(theme.get_palette(1)[0]))
            emb.add_field(name="Speed",value = description)

            # send the embed with the graph image
            file = image_to_file(res_image,"speed.png",emb)
            await ctx.send(file=file,embed=emb)

def setup(client):
    client.add_cog(PxlsSpeed(client))

def get_stats_graph(stats_list:list,title,theme):

    # create the graph
    colors = theme.get_palette(len(stats_list))
    fig = go.Figure(layout=theme.get_layout())
    fig.update_layout(showlegend=False)
    fig.update_layout(title=f"<span style='color:{colors[0]};'>{title}</span>")

    for i,user in enumerate(stats_list):
        # get the data
        name = user[0]
        dates = user[1]
        pixels = user[2]

        # trace the user data
        if theme.has_underglow == True and any( [p == 0 for p in pixels]):
            fig.add_trace(go.Scatter(
                x=dates,
                y=pixels,
                mode='lines',
                name=name,
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
                name=name,
                line=dict(width=4),
                marker=dict(color= colors[i],size=6)
                )
            )

        # add a marge at the right to add the name
        longest_name = max([len(user[0]) for user in stats_list])
        fig.update_layout(margin=dict(r=(longest_name+2)*26))

        # add the name
        fig.add_annotation(
            xanchor='left',
            xref="paper",
            yref="y",
            x = 1.01,
            y = pixels[-1],
            text = ("<b>%s</b>" % name),
            showarrow = False,
            font = dict(color= colors[i],size=40)
        )

    if theme.has_glow == True:
        add_glow(fig,nb_glow_lines=5, alpha_lines=0.5, diff_linewidth=4)

    return fig2img(fig)

def get_grouped_graph(stats_list:list,groupby_opt,title,theme):

    # create the graph and style
    colors = theme.get_palette(len(stats_list))
    fig = go.Figure(layout=theme.get_layout())
    fig.update_yaxes(rangemode='tozero')

    # the title displays the user if there is only 1 in the user_list
    fig.update_layout(title="<span style='color:{};'>{}</span>".format(
        colors[0],title
    ))

    for i,user in enumerate(stats_list):
        # get the data
        dates = user[1]
        pixels = user[2]

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

        name='<span style="color:{};font-size:40;"><b>{}</b></span>'.format(colors[i], user[0])
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

    return fig2img(fig)
