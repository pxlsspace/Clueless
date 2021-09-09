from discord.ext import commands
import plotly.graph_objects as go
from datetime import datetime, timedelta,timezone
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option

from utils.arguments_parser import MyParser
from utils.discord_utils import format_number, image_to_file
from utils.image.image_utils import hex_to_rgb, rgb_to_hex, v_concatenate, is_dark, lighten_color
from utils.table_to_image import table_to_image
from utils.setup import stats, db_stats, GUILD_IDS
from utils.plot_utils import fig2img, add_glow, get_theme
from utils.time_converter import str_to_td, round_minutes_down

class ColorsGraph(commands.Cog):

    def __init__(self, client):
        self.client = client

    @cog_ext.cog_slash(name="colorsgraph",
        description="Show a graph of the canvas colors.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="placed",
            description="To show the graph for the non-virgin pixels only.",
            option_type=5,
            required=False
        ),
        create_option(
            name="last",
            description="Show the progress in the last x year/month/week/day/hour/minute/second. (format: ?y?mo?w?d?h?m?s)",
            option_type=3,
            required=False
        ),
        create_option(
            name="colors",
            description="List of pxls colors separated by a comma.",
            option_type=3,
            required=False
        )]
    )
    async def _colorsgraph(self,ctx:SlashContext, colors=None, placed=False,last=None):
        await ctx.defer()
        args = ()
        if colors:
            args += (colors,)
        if placed:
            args += ("-placed",)
        if last:
            args += ("-last",last)
        await self.colorsgraph(ctx,*args)

    @commands.command(
        name = "colorsgraph",
        aliases=["colorgraph","cg"],
        description = "Show a graph of the canvas colors.",
        usage="[colors] [-placed|-p] [-last ?y?mo?w?d?h?m?s]",
        help = """\t- `<colors>`: list of pxls colors separated by a comma
        \t- `[-placed|-p]`: only show the virgin pixels
        \t- `[-last ?y?mo?w?d?h?m?s]` Show the progress in the last x years/months/weeks/days/hours/minutes/seconds""")
    async def p_colorsgraph(self,ctx,*args):
        async with ctx.typing():
            await self.colorsgraph(ctx,*args)
    
    async def colorsgraph(self,ctx,*args):
        "Show a graph of the canvas colors."
        # parse the arguemnts
        parser  = MyParser(add_help=False)
        parser.add_argument('colors', type=str, nargs='*')
        parser.add_argument('-placed',action='store_true', default=False,
            required=False)
        parser.add_argument('-last',action='store',default=None)
        try:
            parsed_args=  parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f'❌ {e}')

        # check on 'last' param
        if parsed_args.last:
            input_time = str_to_td(parsed_args.last)
            if not input_time:
                return await ctx.send(f"❌ Invalid `last` parameter, format must be `?y?mo?w?d?h?m?s`.")
            dt2 = datetime.now(timezone.utc)
            dt1 = round_minutes_down(datetime.now(timezone.utc) - input_time)
        else:
            dt2 = None
            dt1 = None

        # format colors in a list
        colors = parsed_args.colors
        if parsed_args.colors:
            colors = " ".join(colors).lower()
            colors = colors.split(",")
            colors = [color.strip(" ") for color in colors]

        # init the 'placed' option
        placed_opt = False
        if parsed_args.placed:
            placed_opt = True

        canvas_code = await stats.get_canvas_code()
        data = await db_stats.get_canvas_color_stats(canvas_code,dt1,dt2)

        palette = await db_stats.get_palette(canvas_code)

        # initialise a data dictionary for each color
        data_list = []
        for color in palette:
            color_id = color["color_id"]
            color_name = color["color_name"]
            color_hex = "#" +  color["color_hex"]
            color_dict = dict(color_id=color_id,color_name=color_name,
                color_hex = color_hex, values = [], datetimes = [])
            data_list.append(color_dict)

        # add the data to the dict
        for value in data:
            color_id = value["color_id"]
            dt = value["datetime"]
            if placed_opt:
                pixels = value["amount_placed"]
            else:
                pixels = value["amount"]
            
            data_list[color_id]["values"].append(pixels)
            data_list[color_id]["datetimes"].append(dt)

        if parsed_args.last:
            for d in data_list:
                d["values"] = [v - d["values"][0] for v in d["values"]]
        # create the graph and style
        fig = await self.client.loop.run_in_executor(None,make_color_graph,data_list,colors)
        if fig == None:
            return await ctx.send("❌ Invalid color name.")
        fig.update_layout(
            title="Colors Graph" + (' (non-virgin)' if placed_opt else ""))

        # format the table data
        table_rows = []
        for d in data_list:
            if len(colors) > 0 and not d["color_name"].lower() in colors:
                continue
            diff_time= d["datetimes"][-1] - d["datetimes"][0]
            diff_values= d["values"][-1] - d["values"][0]
            nb_hour = diff_time/timedelta(hours=1)
            speed_per_hour = diff_values/nb_hour
            speed_per_day = speed_per_hour*24
            table_rows.append((
                d["color_name"],
                diff_values,
                format_number(round(speed_per_hour,2)),
                format_number(round(speed_per_day,2)),
                d["color_hex"]
            ))
        table_rows.sort(key = lambda x:x[1],reverse=True)
        table_colors = [row[-1] for row in table_rows]
        table_rows = [row[:-1] for row in table_rows]
        # format the 'progress' value
        for i,row in enumerate(table_rows):
            new_row = list(row)
            new_row[1] = format_number(row[1])
            table_rows[i] = new_row

        table_img = table_to_image(
            table_rows,
            ["Color","Progress","px/h","px/d"],
            ["center","right","right","right"],
            table_colors)

        files = await self.client.loop.run_in_executor(None,fig2file,fig,"colors_graph.png",table_img)
        await ctx.send(files=files)

def make_color_graph(data_list,colors):
    layout = get_theme("default").get_layout()
    fig = go.Figure(layout=layout)
    fig.update_layout(showlegend=False)

    colors_found = False
    for color in data_list:
        if len(colors) > 0 and\
            not color["color_name"].lower() in colors:
            continue
        colors_found = True

        fig.add_trace(go.Scatter(
            x=color["datetimes"],
            y=color["values"],
            mode='lines',
            name=color["color_name"],
            line=dict(width=4),
            marker=dict(color= color["color_hex"]),
        ))

        # add an annotation at the right with the color name
        if is_dark(hex_to_rgb(color["color_hex"])):
            # add an outline to the color name if it's too dark
            text = '<span style = "text-shadow:\
                -{2}px -{2}px 0 {0},\
                {2}px -{2}px 0 {0},\
                -{2}px {2}px 0 {0},\
                {2}px {2}px 0 {0},\
                0px {2}px 0px {0},\
                {2}px 0px 0px {0},\
                -{2}px 0px 0px {0},\
                0px -{2}px 0px {0};"><b>{1}</b></span>'.format(
                    rgb_to_hex(lighten_color(hex_to_rgb(
                        color["color_hex"]),0.4)),
                    color["color_name"],
                    2)
        else:
            text = "<b>%s</b>" % color["color_name"]

        fig.add_annotation(
            xanchor='left',
            xref="paper",
            yref="y",
            x = 1.01,
            y = color["values"][-1],
            text = text,
            showarrow = False,
            font = dict(color= color["color_hex"],size=30)
        )

    if colors_found == False:
        return None

    # add a marge at the right to avoid cropping color names
    longest_name = max([len(c["color_name"]) for c in data_list])
    fig.update_layout(margin=dict(r=(longest_name+2)*20))

    # add a glow to the dark colors
    add_glow(fig,glow_color='lighten_color',dark_only=True,nb_glow_lines=5)
    return fig

def fig2file(fig,title,table_img):

    graph_img = fig2img(fig)
    if table_img.size[0] > table_img.size[1]:
        res_img = v_concatenate(table_img,graph_img,gap_height=20)
        res_file = image_to_file(res_img,title)
        return [res_file]
    else:
        table_file = image_to_file(table_img,"table.png")
        graph_file = image_to_file(graph_img,title)
        return [table_file,graph_file]

def setup(client):
    client.add_cog(ColorsGraph(client))
