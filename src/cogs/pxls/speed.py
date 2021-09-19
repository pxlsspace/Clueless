import plotly.graph_objects as go
import discord
from datetime import datetime, timedelta,timezone
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice

from utils.discord_utils import image_to_file, format_number
from utils.setup import db_stats, db_users, GUILD_IDS
from utils.arguments_parser import parse_speed_args
from utils.table_to_image import table_to_image
from utils.time_converter import format_datetime, format_timezone, round_minutes_down, str_to_td, td_format
from utils.plot_utils import add_glow, get_theme,fig2img, hex_to_rgba_string
from utils.image.image_utils import hex_str_to_int, v_concatenate
from utils.pxls.cooldown import get_best_possible
from utils.timezoneslib import get_timezone

class PxlsSpeed(commands.Cog):

    def __init__(self,client):
        self.client = client

    @cog_ext.cog_slash(
        name="speed",
        description="Show the speed of a pxls user with a graph.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="usernames",
            description="A pxls user name or several ones separated by a space ('!' = your set username.).",
            option_type=3,
            required=False
        ),
        create_option(
            name="last",
            description="Show the speed in the last x year/month/week/day/hour/minute/second. (format: ?y?mo?w?d?h?m?s)",
            option_type=3,
            required=False
        ),
        create_option(
            name="canvas",
            description="To show the speed during the whole canvas.",
            option_type=5,
            required=False
        ),
        create_option(
            name="groupby",
            description="Show a bar chart for each day or hour.",
            option_type=3,
            required=False,
            choices=[
                create_choice(name="month", value="month"),
                create_choice(name="week", value="week"),
                create_choice(name="day", value="day"),
                create_choice(name="hour",value="hour")]
        ),
        create_option(
            name="progress",
            description="To compare the progress.",
            option_type=5,
            required=False
        ),
        create_option(
            name="before",
            description="To show the speed before a specific date (format: YYYY-mm-dd HH:MM)",
            option_type=3,
            required=False
        ),
        create_option(
            name="after",
            description="To show the speed after a specific date (format: YYYY-mm-dd HH:MM)",
            option_type=3,
            required=False
        )]
    )
    async def _speed(self,ctx:SlashContext,usernames=None,last=None,
        canvas=False,groupby=None,progress=False,before=None,after=None):
        await ctx.defer()
        args = ()
        if usernames:
            args += tuple(usernames.split(" "))
        if last:
            args += ("-last",last)
        if canvas:
            args += ("-canvas",)
        if groupby:
            args += ("-groupby",groupby)
        if progress:
            args += ("-progress",)
        if before:
            args += ("-before",) + tuple(before.split(" "))
        if after:
            args += ("-after",) + tuple(after.split(" "))
        await self.speed(ctx,*args)

    @commands.command(
        name="speed",
        usage="<name> [-canvas] [-groupby [hour|day|week|month]] [-progress] [-last <?d?h?m?s>] [-before <date time>] [-after <date time>]",
        description="Show the speed of a pxls user with a graph.",
        help="""- `<names>`: list of pxls users names separated by a space (`!` = your set username)
              - `[-canvas|-c]`: show the canvas stats
              - `[-groupby|-g]`: show a bar chart for each `hour`, `day``, `week` or `month`
              - `[-progress|-p]`: compare the progress between users
              - `[-last ?y?mo?w?d?h?m?s]` Show the progress in the last x years/months/weeks/days/hours/minutes/seconds (default: 1d)
              - `[-before <date time>]`: show the speed before a date and time (format YYYY-mm-dd HH:MM)
              - `[-after <date time>]`: show the speed after a date and time (format YYYY-mm-dd HH:MM)"""
    )
    async def p_speed(self,ctx,*args):
        async with ctx.typing():
            await self.speed(ctx,*args)

    async def speed(self,ctx,*args):
        ''' Show the average speed of a user in the last x min, hours or days '''

        # get the user theme
        discord_user = await db_users.get_discord_user(ctx.author.id)
        user_timezone = discord_user["timezone"]
        current_user_theme = discord_user["color"] or "default"
        theme = get_theme(current_user_theme)

        try:
            param = parse_speed_args(args,get_timezone(user_timezone))
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        # select the discord user's pxls username if it has one linked
        names = param["names"]
        pxls_user_id = discord_user["pxls_user_id"]
        prefix = ctx.prefix if isinstance(ctx,commands.Context) else "/"
        usage_text = f"(You can set your default username with `{prefix}setname <username>`)"

        if len(names) == 0:
            if pxls_user_id == None:
                return await ctx.send("❌ You need to specify at least one username.\n" + usage_text)
            else:
                name = await db_users.get_pxls_user_name(pxls_user_id)
                names.append(name)
        
        if "!" in names:
            if pxls_user_id == None:
                return await ctx.send("❌ You need to have a set username to use `!`.\n" + usage_text)
            else:
                name = await db_users.get_pxls_user_name(pxls_user_id)
                names = [name if u=="!" else u for u in names]

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
                    return await ctx.send(f"❌ Invalid `last` parameter, format must be `?y?mo?w?d?h?m?s`.")
                input_time = input_time + timedelta(minutes=1)
                recent_time = datetime.now(timezone.utc)
                old_time = round_minutes_down(datetime.now(timezone.utc) - input_time)
        else:
            old_time = param["after"] or datetime.min
            recent_time = param["before"] or datetime.max

        # get the data we need
        if groupby_opt:
            (past_time, now_time, stats) = await db_stats.get_grouped_stats_history(
                names, old_time, recent_time,groupby_opt,canvas_opt)
        else:
            (past_time, now_time, stats) = await db_stats.get_stats_history(
                names, old_time,recent_time,canvas_opt)

        # check that we found data
        if len(stats) == 0:
            msg = "❌ User{} not found.".format(
                's' if len(names) >1 else '')
            return await ctx.send(msg)

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
                if groupby_opt == "month":
                    dates = [datetime.strptime(stat["first_datetime"],"%Y-%m-%d %H:%M:%S").strftime("%b %Y") for stat in data]
                    user_timezone = None

                elif groupby_opt == "week":
                    dates = []
                    for stat in data:
                        first_dt = datetime.strptime(stat["first_datetime"],"%Y-%m-%d %H:%M:%S")
                        last_dt = first_dt + timedelta(days=6)
                        week_dates = f"{first_dt.strftime('%d-%b')} - {last_dt.strftime('%d-%b')}"
                        dates.append(week_dates)
                    user_timezone = None

                elif groupby_opt == "day":
                    dates = [stat["first_datetime"][:10] for stat in data]
                    user_timezone = None

                elif groupby_opt == "hour":
                    dates = [stat["first_datetime"][:13] for stat in data]
                    # convert the dates to the user's timezone
                    dates = [datetime.strptime(d,"%Y-%m-%d %H") for d in dates]
                    tz = get_timezone(user_timezone) or timezone.utc
                    dates = [datetime.astimezone(d.replace(tzinfo=timezone.utc),tz) for d in dates]

                pixels = [stat["placed"] for stat in data]
                # remove the "None" values to calculate the min, max, avg
                pixels_int_only = [p for p in pixels if p != None]
                if len(pixels_int_only) > 0:
                    min_pixels = min(pixels_int_only)
                    max_pixels = max(pixels_int_only)
                    average = sum(pixels_int_only)/len(pixels_int_only)
                else:
                    min_pixels = max_pixels = average = None
            else:
                dates = [stat["datetime"] for stat in data]
                if param["progress"]:
                    # substract the first value to each value so they start at 0
                    pixels = [((stat["pixels"] - lowest_pixels)\
                        if (stat["pixels"] != None and lowest_pixels != None) else None)\
                            for stat in data]
                else:
                    pixels = [stat["pixels"] for stat in data]

            user_data =[name,current_pixels,diff_pixels]
            if groupby_opt:
                user_data.append(average)
                user_data.append(min_pixels)
                user_data.append(max_pixels)
            else:
                user_data.append(speed_px_h)
                user_data.append(speed_px_d)
            user_data.append(dates)
            user_data.append(pixels)
            formatted_data.append(user_data)

        if len(formatted_data) == 0:
            msg = "❌ User{} not found{}.".format(
                's' if len(names) >1 else '',
                " (try adding `-c` in the command)" if found_but_no_data else ''
                )
            return await ctx.send(msg)

        # sort the data by the 3rd column (progress in the time frame)
        formatted_data.sort(key = lambda x:x[2],reverse=True)

        # create the headers needed for the table
        table_colors = theme.get_palette(len(formatted_data))

        # make the title
        if groupby_opt:
            title="Speed {}".format(
                "per " + groupby_opt if groupby_opt else "")
        elif canvas_opt and param["last"] == None:
            title = "Canvas Speed"
        else:
            title = "Speed"

        diff_time = round_minutes_down(now_time)-round_minutes_down(past_time)
        diff_time_str = td_format(diff_time)
        
        # get the image of the table
        if groupby_opt:
            # add a "min" and "max" columns if groupby option
            alignments = ["center","right","right","right","right","right"]
            titles = ["Name","Pixels","Progress",f"px/{groupby_opt}","Min","Max"]

        else:
            alignments = ["center","right","right","right","right"]
            titles = ["Name","Pixels","Progress","px/h","px/d"]
        table_data = [d[:-2] for d in formatted_data]

        table_data = [[format_number(c) for c in row] for row in table_data]
        table_image = table_to_image(table_data,titles,
        alignments,table_colors,theme=theme)

        # create the graph
        graph_data = [[d[0],d[-2],d[-1]] for d in formatted_data]
        if groupby_opt:
            graph_image = await self.client.loop.run_in_executor(None,
                get_grouped_graph,graph_data,title,theme,user_timezone)
        else:
            graph_image = await self.client.loop.run_in_executor(None,
                get_stats_graph,graph_data,title,theme,user_timezone)

        # merge the table image and graph image
        res_image = v_concatenate(table_image,graph_image,gap_height=20)

        # calculate the best possbile amount in the time frame
        best_possible,average_cooldown = await get_best_possible(past_time,now_time)

        # create the embed
        description = f"• Between {format_datetime(past_time)} and {format_datetime(now_time)}\n"
        description += f"• Time: `{diff_time_str}`\n"
        description += f"• Average cooldown: `{round(average_cooldown,2)}` seconds\n"
        description += f"• Best possible (without stack): ~`{format_number(best_possible)}` pixels."
        emb = discord.Embed(color=hex_str_to_int(theme.get_palette(1)[0]))
        emb.add_field(name=title,value = description)

        # send the embed with the graph image
        file = image_to_file(res_image,"speed.png",emb)
        await ctx.send(file=file,embed=emb)

def setup(client):
    client.add_cog(PxlsSpeed(client))

def get_stats_graph(stats_list:list,title,theme,user_timezone=None):

    # get the timezone informations
    tz = get_timezone(user_timezone)
    if tz == None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    # create the graph
    colors = theme.get_palette(len(stats_list))
    fig = go.Figure(layout=theme.get_layout(annotation_text=annotation_text))
    fig.update_layout(showlegend=False)
    fig.update_layout(title=f"<span style='color:{colors[0]};'>{title}</span>")

    for i,user in enumerate(stats_list):
        # get the data
        name = user[0]
        dates = user[1]
        pixels = user[2]

        # convert the dates to the user timezone
        dates = [datetime.astimezone(d.replace(tzinfo=timezone.utc),tz) for d in dates]

        # trace the user data
        if theme.has_underglow == True and any( [(p != None and p <= 100) for p in pixels]):
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

def get_grouped_graph(stats_list:list,title,theme,user_timezone=None):

    # get the timezone informations
    tz = get_timezone(user_timezone)
    if tz == None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    # create the graph and style
    colors = theme.get_palette(len(stats_list))
    fig = go.Figure(layout=theme.get_layout(annotation_text=annotation_text))
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
