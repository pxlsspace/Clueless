from discord.ext import commands
import plotly.graph_objects as go
from datetime import datetime, timedelta,timezone

from utils.arguments_parser import MyParser
from utils.discord_utils import format_number, image_to_file
from utils.image_utils import hex_to_rgb, rgb_to_hex, v_concatenate
from utils.table_to_image import is_dark, lighten_color, table_to_image
from utils.setup import stats, db_stats_manager as db_stats
from utils.plot_utils import fig2img, layout
from utils.time_converter import str_to_td, round_minutes_down

class ColorsGraph(commands.Cog):

    def __init__(self, client):
        self.client = client

    @commands.command(
        aliases=["colorgraph","cg"],
        description = "Show a graph of the canvas colors.",
        usage="[colors] [-placed|-p] [-last ?d?h?m?s]",
        help = """\t- `<colors>`: list of pxls colors separated by a comma
        \t- `[-placed|-p]`: only show the virgin pixels
        \t- `[-last ?d?h?m?s]` Show the progress in the last x days/hour/min/s""")
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
                return await ctx.send(f"❌ Invalid `last` parameter, format must be `?d?h?m?s`.")
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

        async with ctx.typing():
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
                title="Colors Graph" + (' (placed)' if placed_opt else ""))

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
                ["Color","Progress","px/h","pxs/d"],
                ["center","right","right","right"],
                table_colors)

            files = await self.client.loop.run_in_executor(None,fig2file,fig,"colors_graph.png",table_img)
            await ctx.send(files=files)

def make_color_graph(data_list,colors):
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
    if len(colors) > 0:
        add_glow(fig,glow_color='lighten_color')
    else:
        add_glow(fig,glow_color='lighten_color',dark_only=True)
    return fig

def add_glow(fig:go.Figure,nb_glow_lines=10,diff_linewidth=1.5,alpha_lines=0.5,
    glow_color="line_color",dark_only=False):
    """Add a glow effect to all the lines in a Figure object.
    
    Each existing line is redrawn several times with increasing width and low
    alpha to create the glow effect.
    """
    alpha_value = alpha_lines/nb_glow_lines

    for trace in fig.select_traces():
        x = trace.x
        y = trace.y
        mode = trace.mode
        line_width = trace.line.width
        line_color = trace.marker.color

        # skip the color if dark_only is true and the color is not dark
        if dark_only and not is_dark(hex_to_rgb(line_color)):
            continue

        if glow_color == "line_color":
            color = line_color

        elif glow_color == "lighten_color":
            # lighten only the dark colors
            if is_dark(hex_to_rgb(line_color)):
                color = rgb_to_hex(lighten_color(hex_to_rgb(line_color),0.2))
            else:
                color = line_color
        else:
            color = glow_color

        # add the glow
        for n in range(nb_glow_lines):
            fig.add_trace(go.Scatter(
                x = x,
                y = y,
                mode = mode,
                line=dict(width=line_width + (diff_linewidth*n)),
                marker=dict(color = hex_to_rgba_string(color,alpha_value))
            ))

        # add the original trace over the glow
        fig.add_trace(go.Scatter(
            x = x,
            y = y,
            mode = mode,
            line=dict(width=line_width),
            marker=dict(color = line_color)
        ))

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

def hex_to_rgba_string(hex:str,alpha_value=1) ->str:
    """ '#ffffff' -> 'rgba(255,255,255,alpha_value)' """
    hex = hex.strip("#")

    rgb = tuple([int(hex[i:i+2],16) for i in range(0, len(hex), 2)])
    rgba = rgb + (alpha_value,)

    return "rgba" + str(rgba)

def setup(client):
    client.add_cog(ColorsGraph(client))
