import discord
from datetime import datetime
from discord.ext import commands
import plotly.graph_objects as go
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice
from datetime import timezone

from utils.arguments_parser import MyParser
from utils.image.image_utils import hex_str_to_int
from utils.time_converter import format_datetime, str_to_td, format_timezone
from utils.discord_utils import image_to_file
from utils.pxls.cooldown import get_cd
from utils.plot_utils import add_glow, get_theme, fig2img, hex_to_rgba_string
from utils.setup import stats, db_stats, db_users, GUILD_IDS
from utils.timezoneslib import get_timezone

class Online(commands.Cog):

    def __init__(self,client) -> None:
        self.client = client

    @cog_ext.cog_slash(name="online",
                description="Show the online count history.",
                guild_ids=GUILD_IDS,
                options=[
                create_option(
                    name= "cooldown",
                    description= "To show the cooldown instead of the online count.",
                    option_type=5,
                    required=False
                ),
                create_option(
                    name="last",
                    description="A time duration in the format ?y?mo?w?d?h?m?s.",
                    option_type=3,
                    required=False
                ),
                create_option(
                    name="canvas",
                    description="To show the count during the current canvas.",
                    option_type=5,
                    required=False
                ),
                create_option(
                    name="groupby",
                    description="To show a bar graph with the average of each day or hour",
                    option_type=3,
                    required=False,
                    choices=[
                        create_choice(name="day", value="day"),
                        create_choice(name="hour", value="hour")
                    ]
                )]
            )
    async def _online(self,ctx:SlashContext, cooldown=False,last=None,canvas=False,groupby=None):
        await ctx.defer()
        args = ()
        if cooldown:
            args += ("-cooldown",)
        if last:
            args += ("-last",last)
        if canvas:
            args += ("-canvas",)
        if groupby:
            args += ("-groupby",groupby)
        await self.online(ctx,*args)
    
    @commands.command(
        name = "online",
        description = "Show the online count history.",
        usage = "[-cooldown] [-canvas] [-groupby day/hour] [-last ?y?mo?w?d?h?m?s]",
        help = """- `[-cooldown|-cd]`: show the cooldown instead of online count
                - `[-canvas|-c]`: show the count during the whole canvas
                - `[-groupby|-g]`: show a bar graph with the average of each `day` or `hour`
                - `[-last|-l ?y?mo?w?d?h?m?s]` Show the count in the last x years/months/weeks/days/hours/minutes/seconds (default: 1d)""")
    async def p_online(self,ctx,*args):
        async with ctx.typing():
            await self.online(ctx,*args)

    async def online(self,ctx,*args):
        # parse the arguemnts
        parser  = MyParser(add_help=False)
        parser.add_argument('-last','-l',action='store',default=None)
        parser.add_argument('-cooldown',"-cd", action='store_true', default=False)
        parser.add_argument('-canvas','-c', action='store_true', default=False)
        parser.add_argument("-groupby",'-g',choices=['day','hour'],required=False)
        try:
            parsed_args= parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        if parsed_args.last == None and parsed_args.canvas == True:
            last = "10000d"
        elif parsed_args.last == None:
            last = "1d"
        else:
            last = parsed_args.last

        # get the user theme
        discord_user = await db_users.get_discord_user(ctx.author.id)
        user_timezone = discord_user["timezone"]
        current_user_theme = discord_user["color"] or "default"
        theme = get_theme(current_user_theme)

        input_time = str_to_td(last)
        if not input_time:
            return await ctx.send(f"❌ Invalid `last` parameter, format must be `?y?mo?w?d?h?m?s`.")

        data = await db_stats.get_general_stat("online_count",
            datetime.utcnow()-input_time,datetime.utcnow(),parsed_args.canvas)
        current_count = stats.online_count

        if parsed_args.groupby:
            groupby = parsed_args.groupby
            if groupby == "day":
                format = "%Y-%m-%d"
                user_timezone = None
            elif groupby == "hour":
                format = "%Y-%m-%d %H"

            # group by the format
            data_dict = {}
            for d in data:
                if d[0] != None:
                    date_str = d["datetime"].strftime(format)
                    key = datetime.strptime(date_str,format)
                    if key in data_dict:
                        data_dict[key].append(int(d[0]))
                    else:
                        data_dict[key] = [int(d[0])]

            # get the average for each date
            dates = []
            online_counts = []
            for key, counts in data_dict.items():
                average = sum(counts)/len(counts)
                average = round(average,2)
                dates.append(key)
                online_counts.append(average)
            if len(dates) <= 1:
                return await ctx.send("❌ The time frame given is too short.")
            dates = dates[:-1]
            online_counts = online_counts[:-1]
        else:
            online_counts = [int(e[0]) for e in data if e[0] != None]
            dates = [e[1] for e in data if e[0] != None]
            online_counts.insert(0,int(current_count))
            dates.insert(0,datetime.utcnow())

        # make graph title
        if parsed_args.cooldown:
            title = "Pxls Cooldown"
        else:
            title = "Online Count"
        
        # get the cooldown for each online value if we have the cooldown arg
        if parsed_args.cooldown:
            online_counts = [round(get_cd(count),2) for count in online_counts]
            current_count = round(get_cd(current_count),2)

        # make graph
        if parsed_args.groupby:
            fig = await self.client.loop.run_in_executor(None,
                make_grouped_graph,dates,online_counts,theme,user_timezone)
        else:
            fig = await self.client.loop.run_in_executor(None,
                make_graph,dates,online_counts,theme,user_timezone)
        fig.update_layout(title="<span style='color:{};'>{}</span>".format(
            theme.get_palette(1)[0],
            title + (f" (average per {groupby})" if parsed_args.groupby else "")))

        # make embed
        img = await self.client.loop.run_in_executor(None,fig2img,fig)
        description = '• Between {} and {}\n• Current {}: `{}`\n• Average: `{}`\n• Min: `{}` • Max: `{}`'.format(
                format_datetime(dates[-1]),
                format_datetime(dates[0]),
                title,
                current_count,
                round(sum(online_counts)/len(online_counts),2),
                min(online_counts),
                max(online_counts)
            )
        emb = discord.Embed(
            title = title,
            color=hex_str_to_int(theme.get_palette(1)[0]),
            description = description
        )

        file = image_to_file(img,"online_count.png",emb)
        await ctx.send(embed=emb,file=file)

def make_graph(dates,values,theme,user_timezone=None):

    # get the timezone informations
    tz = get_timezone(user_timezone)
    if tz == None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    dates = [datetime.astimezone(d.replace(tzinfo=timezone.utc),tz) for d in dates]

    # create the graph
    fig = go.Figure(layout=theme.get_layout(annotation_text=annotation_text))
    fig.update_layout(showlegend=False)

    # trace the data
    fig.add_trace(go.Scatter(
        x=dates,
        y=values,
        mode='lines',
        name="Online Count",
        line=dict(width=4),
        marker=dict(color= theme.get_palette(1)[0],size=6)
        )
    )

    if theme.has_glow:
        add_glow(fig,nb_glow_lines=5, alpha_lines=0.5, diff_linewidth=4)
    if theme.has_underglow:
        fig.add_trace(go.Scatter(
            x=dates,
            y=[min(values)]*len(values),
            mode='lines',
            marker=dict(color= 'rgba(0,0,0,0)',size=0),
            fill = 'tonexty',
            fillcolor=hex_to_rgba_string(theme.get_palette(1)[0],0.06)
        ))
    return fig

def make_grouped_graph(dates,values,theme,user_timezone=None):

 # get the timezone informations
    tz = get_timezone(user_timezone)
    if tz == None:
        tz = timezone.utc
        annotation_text = "Timezone: UTC"
    else:
        annotation_text = f"Timezone: {format_timezone(tz)}"

    dates = [datetime.astimezone(d.replace(tzinfo=timezone.utc),tz) for d in dates]

    # create the graph and style
    color = theme.get_palette(1)[0]
    fig = go.Figure(layout=theme.get_layout(annotation_text=annotation_text))
    fig.update_yaxes(rangemode='tozero')

    # add an outline of the bg color to the text above the bars
    text = ['<span style = "text-shadow:\
    -{2}px -{2}px 0 {0},\
    {2}px -{2}px 0 {0},\
    -{2}px {2}px 0 {0},\
    {2}px {2}px 0 {0},\
    0px {2}px 0px {0},\
    {2}px 0px 0px {0},\
    -{2}px 0px 0px {0},\
    0px -{2}px 0px {0};">{1}</span>'.format(theme.background_color,v,2) for v in values]

    # trace the user data
    if theme.has_underglow == True:
        # different style if the theme has underglow
        fig.add_trace(
            go.Bar(
                name="Online Count",
                x = dates,
                y = values,
                text = text,
                textposition = 'outside',
                marker_color = hex_to_rgba_string(color,0.15),
                marker_line_color =color,
                marker_line_width=2.5,
                textfont = dict(color=color, size=40),
                cliponaxis = False
            )
        )
    else:
        fig.add_trace(
            go.Bar(
                name="Online Count",
                x = dates,
                y = values,
                text = text,
                textposition = 'outside',
                marker = dict(color=color, opacity=0.9),
                textfont = dict(color=color, size=40),
                cliponaxis = False
            )
        )
    return fig


def setup(client):
    client.add_cog(Online(client))
    