import discord
import pandas as pd
from PIL import Image
from datetime import timezone
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice
from datetime import datetime, timedelta

from main import tracked_templates
from utils.discord_utils import format_number, image_to_file, UserConverter
from utils.pxls.template_manager import get_template_from_url, parse_template
from utils.setup import GUILD_IDS, db_templates, db_users
from utils.timezoneslib import get_timezone
from utils.utils import make_progress_bar
from utils.time_converter import round_minutes_down, str_to_td, td_format, format_datetime
from utils.table_to_image import table_to_image
from utils.arguments_parser import MyParser
from utils.plot_utils import get_theme, get_gradient_palette
from cogs.pxls.speed import get_grouped_graph, get_stats_graph
from utils.image.image_utils import v_concatenate


class Progress(commands.Cog):
    def __init__(self, client) -> None:
        self.client = client

    @commands.group(
        name="progress",
        description="Track a template over time.",
        aliases=["prog"],
        invoke_without_command=True,
    )
    async def progress(self, ctx, template=None):
        if template:
            async with ctx.typing():
                await self.check(ctx, template)
        else:
            await ctx.send("Usage: `>progress [check|list|add|remove|update]`")

    @cog_ext.cog_subcommand(
        base="progress",
        name="check",
        description="Check the progress of a template.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="template",
                description="The name or URL of the template you want to check.",
                option_type=3,
                required=True,
            ),
        ],
    )
    async def _check(self, ctx: SlashContext, template):
        await ctx.defer()
        await self.check(ctx, template)

    @progress.command(
        name="check", description="Check the progress of a template.", usage="<url|name>"
    )
    async def p_check(self, ctx, template: str):

        async with ctx.typing():
            await self.check(ctx, template)

    async def check(self, ctx, template_input):
        # check if the input is an URL or template name
        if parse_template(template_input) is not None:
            try:
                template = await get_template_from_url(template_input)
            except ValueError as e:
                return await ctx.send(f":x: {e}")
            # check if we have a tracked template with the same image and coords
            template_with_same_image = tracked_templates.check_duplicate_template(template)
            if template_with_same_image:
                template = template_with_same_image
                is_tracked = True
            else:
                is_tracked = False
        else:
            template = tracked_templates.get_template(template_input, None, False)
            if template is None:
                return await ctx.send(f":x: There is no template with the name `{template_input}` in the tracker.")
            is_tracked = True

        # get the current template progress stats
        title = template.title or "`N/A`"
        total_placeable = template.total_placeable
        correct_pixels = template.update_progress()
        progress_image = template.get_progress_image()

        if total_placeable == 0:
            return await ctx.send(
                ":x: The template seems to be outside the canvas, make sure it's correctly positioned."
            )
        correct_percentage = round((correct_pixels / total_placeable) * 100, 2)
        togo_pixels = total_placeable - correct_pixels

        # make the progress bar
        bar = make_progress_bar(correct_percentage)

        # format the progress stats
        total_placeable = int(total_placeable)
        correct_pixels = int(correct_pixels)
        togo_pixels = int(togo_pixels)

        embed = discord.Embed(title="**Progress Check**", color=0x66C5CC)
        embed.set_thumbnail(url="attachment://template_image.png")

        info_text = f"Title: `{title}`\n"
        if template.name:
            info_text += f"Name: `{template.name}`\n"
        info_text += f"Link: [click to open]({template.url})\n"

        embed.add_field(name="**Info**", value=info_text, inline=False)

        progress_text = f"Correct pixels: `{format_number(correct_pixels)}`/`{format_number(total_placeable)}`\n"
        progress_text += f"Pixels to go: `{format_number(togo_pixels)}`\n"
        progress_text += f"Progress:\n**|`{bar}`|** `{correct_percentage}%`\n"
        embed.add_field(name="**Current Progress**", value=progress_text, inline=False)

        if is_tracked:
            timeframes = [{"minutes": 5}, {"hours": 1}, {"hours": 6}, {"days": 1}, {"days": 7}]
            timeframe_names = ["5 minutes", "hour", "6 hours", "day", "week"]
            now = round_minutes_down(datetime.utcnow(), 5)
            last_progress = await db_templates.get_template_progress(template, now)
            values = ""
            for i, tf in enumerate(timeframes):
                td = timedelta(**tf)
                tf_progress = await db_templates.get_template_progress(template, now - td)
                if tf_progress is None or last_progress is None:
                    delta_progress = "`N/A`"
                else:
                    delta_progress = last_progress["progress"] - tf_progress["progress"]
                values += "• Last {}: `{}` px\n".format(
                    timeframe_names[i],
                    format_number(delta_progress),
                )
            oldest_record = await db_templates.get_template_oldest_progress(template)
            if oldest_record and oldest_record["datetime"]:
                oldest_record_time = oldest_record['datetime']
                oldest_record_time.replace(tzinfo=timezone.utc)
                oldest_progress = oldest_record["progress"]
                progress_since_tracking = correct_pixels - oldest_progress
                tracking_time = datetime.utcnow() - oldest_record_time
                if tracking_time != timedelta(0):
                    speed_px_h = (progress_since_tracking / (tracking_time / timedelta(hours=1)))
                    speed_px_d = (progress_since_tracking / (tracking_time / timedelta(days=1)))
                    values += "• Average: `{}` px/day\n(`{}` px/hour)".format(
                        format_number(speed_px_d),
                        format_number(speed_px_h),
                    )
            else:
                # if there is no data for this template in the db, the starting tracking time is now
                oldest_record_time = datetime.now(timezone.utc)
            embed.add_field(name="**Speed:**", value=values, inline=False)

            owner = self.client.get_user(template.owner_id)
            embed.set_footer(text=f"Owner • {owner}\nTracking Since")
            embed.timestamp = oldest_record_time
        else:
            prefix = ctx.prefix if isinstance(ctx, commands.Context) else "/"
            embed.set_footer(text=f"[Not Tracked]\nUse {prefix}progress add <name> <url> to start tracking.")
        detemp_file = image_to_file(progress_image, "progress.png", embed)
        template_file = image_to_file(Image.fromarray(template.image_array), "template_image.png")
        await ctx.send(files=[template_file, detemp_file], embed=embed)

    @cog_ext.cog_subcommand(
        base="progress",
        name="add",
        description="Add a template to the tracker.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="name",
                description="The name of the template.",
                option_type=3,
                required=True,
            ),
            create_option(
                name="url",
                description="The URL of the template.",
                option_type=3,
                required=True,
            ),
        ]
    )
    async def _add(self, ctx: SlashContext, name: str, url: str):
        await ctx.defer()
        await self.add(ctx, name, url)

    @progress.command(
        name="add", description="Add a template to the tracker.", usage="<name> <URL>"
    )
    async def p_add(self, ctx, name: str, url: str, args=None):
        async with ctx.typing():
            await self.add(ctx, name, url)

    async def add(self, ctx, name, url):
        try:
            template = await get_template_from_url(url)
        except ValueError as e:
            return await ctx.send(f":x: {e}")

        if template.total_placeable == 0:
            return await ctx.send(
                ":x: The template seems to be outside the canvas, make sure it's correctly positioned."
            )
        template.update_progress()
        try:
            await tracked_templates.save(template, name, ctx.author.id)
        except ValueError as e:
            return await ctx.send(f":x: {e}")
        return await ctx.send(f"✅ Template `{name}` added to the tracker.")

    sort_options = ["Name", "Size", "Correct", "To Go", "%", "px/h (last 1h)", "px/h (last 6h)", "px/h (last 1d)", "px/h (last 7d)"]

    @cog_ext.cog_subcommand(
        base="progress",
        name="list",
        description="Show all the public tracked templates.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="sort",
                description="Sort the table by the chosen column. (default: px/h (last 1h))",
                option_type=3,
                required=False,
                choices=[create_choice(name=c, value=str(i)) for i, c in enumerate(sort_options)],
            )
        ]
    )
    async def _list(self, ctx: SlashContext, sort=None):
        await ctx.defer()
        if sort:
            sort = int(sort)
        await self.list(ctx, sort)

    @progress.command(
        name="list",
        description="Show all the public tracked templates.",
        aliases=["ls"],
        usage="[-sort <column>]",
        help="""
        `[-sort <column>]`: Sort the table by the chosen column
        The choices are :
            - `name`: the template name
            - `size`: the total placeable pixels
            - `correct`: the number of correct pixels
            - `togo`: the number of pixels left to place
            - `%`: the completion percentage
            - `last1h`: the speed in the last hour
            - `last6h`: the speed in the last 6 hours
            - `last1d`: the speed in the last day
            - `last7d`: the speed in the last week
        (default: `last1h`)
        """,
    )
    async def p_list(self, ctx, *args):
        parser = MyParser(add_help=False)
        sort_options = ["name", "size", "correct", "togo", "%", "last1h", "last6h", "last1d", "last7d"]

        parser.add_argument("-sort", "-s", choices=sort_options, required=False)
        try:
            parsed_args = parser.parse_args(args)
        except Exception as error:
            return await ctx.send(f"❌ {error}")
        if parsed_args.sort:
            sort = sort_options.index(parsed_args.sort)
        else:
            sort = None
        async with ctx.typing():
            await self.list(ctx, sort)

    async def list(self, ctx, sort=None):
        public_tracked_templates = tracked_templates.get_all_public_templates()
        if len(public_tracked_templates) == 0:
            return await ctx.send("No templates tracked :'(")

        titles = ["Name", "Size", "Correct", "To Go", "%", "px/h (last 1h)", "px/h (last 6h)", "px/h (last 1d)", "px/h (last 7d)"]
        if sort is None:
            sort = 5
        # make the embed base
        embed = discord.Embed(title="Tracked Templates", color=0x66C5CC)
        embed.description = "Sorted By: `{}`\nTotal Templates: `{}`".format(
            titles[sort],
            len(public_tracked_templates),
        )
        last_updated = await db_templates.get_last_update_time()
        if last_updated:
            embed.set_footer(text="Last Updated")
            embed.timestamp = last_updated

        # gather the templates data
        table = []
        now = round_minutes_down(datetime.utcnow(), 5)
        for template in public_tracked_templates:
            line_colors = [None, None, None, None]
            # template info
            name = template.name
            total = template.total_placeable
            # last progress
            last_progress = await db_templates.get_template_progress(template, now)
            if not last_progress:
                current_progress = togo = percentage = "N/A"
                line_colors.append(None)
            else:
                current_progress = last_progress["progress"]
                togo = total - current_progress
                percentage = (current_progress / total) * 100
                line_colors.append(get_percentage_color(percentage))

            # timeframes speeds
            timeframes = [{"hours": 1}, {"hours": 6}, {"days": 1}, {"days": 7}]
            values = []
            for tf in timeframes:
                td = timedelta(**tf)
                tf_progress = await db_templates.get_template_progress(template, now - td)
                if not tf_progress or not last_progress:
                    values.append("N/A")
                    line_colors.append(None)
                else:
                    delta_progress = last_progress["progress"] - tf_progress["progress"]
                    delta_time = last_progress["datetime"] - tf_progress["datetime"]
                    if delta_time == timedelta(0):
                        values.append("N/A")
                        line_colors.append(None)
                    else:
                        # speed in pixels / hour
                        speed_px_h = delta_progress / (delta_time / timedelta(hours=1))
                        values.append(speed_px_h)
                        line_colors.append(get_speed_color(speed_px_h))

            table.append([name, total, current_progress, togo, percentage] + values + [line_colors])

        table.sort(key=lambda x: (x[sort] is not None and not(isinstance(x[sort], str)), x[sort]), reverse=True)
        table_data = [line[:-1] for line in table]
        table_colors = [line[-1] for line in table]
        table_data = [[format_number(c) for c in row] for row in table_data]
        theme = get_theme("default")
        theme.outline_dark = False
        table_image = table_to_image(table_data, titles, colors=table_colors, theme=theme)
        table_file = image_to_file(table_image, "progress.png", embed=embed)
        await ctx.send(embed=embed, file=table_file)

    @cog_ext.cog_subcommand(
        base="progress",
        name="update",
        description="Update a template in the tracker.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="name",
                description="The name of the template you want to update.",
                option_type=3,
                required=True,
            ),
            create_option(
                name="new_url",
                description="The new URL of the template.",
                option_type=3,
                required=False,
            ),
            create_option(
                name="new_name",
                description="The new name of the template.",
                option_type=3,
                required=False,
            ),
            create_option(
                name="new_owner",
                description="The new owner of the template.",
                option_type=6,
                required=False,
            ),
        ]
    )
    async def _update(self, ctx: SlashContext, name, new_url=None, new_name=None, new_owner=None):
        await ctx.defer()
        if new_owner:
            new_owner_id = new_owner.id
        else:
            new_owner_id = None
        await self.update(ctx, name, new_url, new_name, new_owner_id)

    @progress.command(name="update", description="Update the template URL.", usage="<current name> <new url>")
    async def p_update_url(self, ctx, current_name, new_url):
        async with ctx.typing():
            await self.update(ctx, current_name, new_url=new_url)

    @progress.command(name="rename", description="Update the template name.", usage="<current name> <new name>")
    async def p_update_name(self, ctx, current_name, new_name):
        async with ctx.typing():
            await self.update(ctx, current_name, new_name=new_name)

    @progress.command(name="transfer", description="Transfer the template ownernership.", usage="<current name> <new owner>")
    async def p_update_owner(self, ctx, current_name, new_owner):
        try:
            new_user = await UserConverter().convert(ctx, new_owner)
        except commands.UserNotFound as e:
            return await ctx.send(f"❌ {e}")

        async with ctx.typing():
            await self.update(ctx, current_name, new_owner_id=new_user.id)

    async def update(self, ctx, current_name, new_url=None, new_name=None, new_owner_id=None):
        try:
            await tracked_templates.update_template(current_name, ctx.author.id, new_url, new_name, new_owner_id)
        except Exception as e:
            return await ctx.send(f":x: {e}")
        return await ctx.send("✅ Template updated.")

    @cog_ext.cog_subcommand(
        base="progress",
        name="delete",
        description="Remove a template from the tracker.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="template",
                description="The name the template you want to delete.",
                option_type=3,
                required=True,
            ),
        ],
    )
    async def _delete(self, ctx: SlashContext, template):
        await ctx.defer()
        await self.delete(ctx, template)

    @progress.command(
        name="delete",
        description="Delete a template from the tracker.",
        usage="<template>",
        aliases=["remove", "del"],
    )
    async def p_delete(self, ctx, template: str):
        async with ctx.typing():
            await self.delete(ctx, template)

    async def delete(self, ctx, template_name):
        try:
            await tracked_templates.delete_template(template_name, ctx.author.id, False)
        except Exception as e:
            return await ctx.send(f":x: {e}")
        return await ctx.send("✅ Template deleted.")

    @cog_ext.cog_subcommand(
        base="progress",
        name="speed",
        description="Check the speed graph of a tracked template.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="template",
                description="The name the template you want to check.",
                option_type=3,
                required=True,
            ),
            create_option(
                name="last",
                description="Show the progress in the last x year/month/week/day/hour/minute/second. (format: ?y?mo?w?d?h?m?s)",
                option_type=3,
                required=False,
            ),
            create_option(
                name="groupby",
                description="Show a bar chart for each 5 min interval, hour or day.",
                option_type=3,
                required=False,
                choices=[
                    create_choice(name="5min", value="5min"),
                    create_choice(name="hour", value="hour"),
                    create_choice(name="day", value="day"),

                ],
            ),
        ],
    )
    async def _speed(self, ctx: SlashContext, template, last=None, groupby=None):
        await ctx.defer()
        await self.speed(ctx, template, last, groupby)

    @progress.command(
        name="speed",
        description="Check the speed graph of a tracked template.",
        usage="<template> [-last ?y?mo?w?d?h?m?s] [-groupby 5min]",
    )
    async def p_speed(self, ctx, *args):
        # parse the arguemnts
        parser = MyParser(add_help=False)
        parser.add_argument("template", action="store")
        parser.add_argument("-last", "-l", action="store", default=None)
        parser.add_argument("-groupby", "-g", choices=["5min", "hour", "day"], required=False)

        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        async with ctx.typing():
            await self.speed(ctx, parsed_args.template, parsed_args.last, parsed_args.groupby)

    async def speed(self, ctx, template_name, last: str = None, groupby: str = None):
        # get the template
        try:
            template = tracked_templates.get_template(template_name)
        except Exception as e:
            return await ctx.send(f":x: {e}")
        if template is None:
            return await ctx.send(f"No template named `{template_name}` found.")

        # check on the "last" option
        if last is None:
            dt1 = datetime.min
            dt2 = datetime.max
        else:
            input_time = str_to_td(last)
            if not input_time:
                return await ctx.send(
                    "❌ Invalid `last` parameter, format must be `?y?mo?w?d?h?m?s`."
                )
            dt2 = datetime.now(timezone.utc)
            dt1 = round_minutes_down(dt2 - input_time, step=5) - timedelta(minutes=1)

        # get the user theme and timezone
        discord_user = await db_users.get_discord_user(ctx.author.id)
        current_user_theme = discord_user["color"] or "default"
        theme = get_theme(current_user_theme)
        user_timezone_name = discord_user["timezone"]
        user_timezone = get_timezone(user_timezone_name)

        # get the data
        template_stats = await db_templates.get_all_template_data(template, dt1, dt2)
        if not template_stats:
            return await ctx.send(":x: Couldn't find any data for this template.")
        template_stats = list([list(r) for r in template_stats])
        df = pd.DataFrame(template_stats, columns=["datetime", "progress"])
        df = df.set_index("datetime")

        dates = [d.to_pydatetime() for d in df.index.tolist()]
        values = df['progress'].tolist()

        oldest_progress = values[0]
        oldest_time = dates[0]
        latest_progress = values[-1]
        latest_time = dates[-1]

        if groupby:
            # set the datetimes to the correct user time zone
            df = df.tz_localize("UTC").tz_convert(user_timezone)
            df = df.diff()

            if groupby == "5min":
                dates = [d.to_pydatetime() for d in df.index.tolist()]
                values = df['progress'].tolist()
                values.pop(0)
                oldest_time = dates.pop(0)
            else:
                if groupby == "hour":
                    format = "%Y-%m-%d %H"
                elif groupby == "day":
                    format = "%Y-%m-%d"
                else:
                    return await ctx.send(":x: Invalid `groupby` option.")

                df = df.groupby(df.index.strftime(format))["progress"].sum()
                dates = [datetime.strptime(d, format) for d in df.index.tolist()]
                values = df.values
                oldest_time = dates[0]
                if dt1 != datetime.min:
                    values = values[1:]
                    dates = dates[1:]

            if len(dates) == 0 or len(values) == 0:
                return await ctx.send(":x: The time frame given is too short.")
            values = [int(v) for v in values]

        delta_time = latest_time - oldest_time

        if groupby:
            # calculate the speed as px/<groupby>
            delta_progress = sum(values)
            average_speed = sum(values) / len(values)
            min_value = min(values)
            max_value = max(values)
        else:
            # calculate the speed (between the given dates)
            delta_progress = latest_progress - oldest_progress

            if delta_time == timedelta(0):
                return await ctx.send(":x: The time frame given is too short.")
            else:
                speed_px_h = (delta_progress / (delta_time / timedelta(hours=1)))
                speed_px_d = (delta_progress / (delta_time / timedelta(days=1)))

        # make the graph
        if not groupby:
            graph_image = get_stats_graph(
                [[template.name, dates, values]],
                "Template Speed",
                theme,
                user_timezone_name,
            )
        else:
            graph_image = get_grouped_graph(
                [[template.name, dates, values]],
                f"Template speed (grouped by {groupby})",
                theme,
                user_timezone_name,
            )

        # make the table
        if groupby:
            table_data = [[template.name, template.total_placeable, delta_progress, average_speed, min_value, max_value]]
            titles = ["Name", "Size", "Progress", f"px/{groupby}", "min", "max"]
            alignments = ["center", "right", "right", "right", "right", "right"]
        else:
            table_data = [[template.name, template.total_placeable, delta_progress, speed_px_h, speed_px_d]]
            titles = ["Name", "Size", "Progress", "px/h", "px/d"]
            alignments = ["center", "right", "right", "right", "right"]
        table_data = [[format_number(c) for c in row] for row in table_data]
        colors = theme.get_palette(1)
        table_image = table_to_image(table_data, titles, alignments, colors, theme)

        # make the embed
        embed = discord.Embed(title="**Template Speed**", color=0x66C5CC)
        embed.description = "• Between {} and {}\n".format(
            format_datetime(oldest_time),
            format_datetime(latest_time),
        )
        embed.description += "• Time: `{}`".format(td_format(delta_time, hide_seconds=True))

        # merge the table image and graph image
        res_image = v_concatenate(table_image, graph_image, gap_height=20)
        res_file = image_to_file(res_image, "template_speed.png", embed)

        await ctx.send(embed=embed, file=res_file)


pos_speed_palette = get_gradient_palette(["#ffffff", "#70dd13", "#31a117"], 101)
neg_speed_palette = get_gradient_palette(["#ff6474", "#ff0000", "#991107"], 101)
percentage_palette = get_gradient_palette(["#ff3b3b", "#fff491", "#beff40", "#70dd13", "#31a117"], 101)


def get_speed_color(speed, max_speed=600, min_speed=-400):
    if speed >= 0:
        palette_idx = min(speed, max_speed)
        palette_idx = palette_idx / max_speed
        palette_idx = int(palette_idx * (len(pos_speed_palette) - 1))
        return pos_speed_palette[palette_idx]
    elif speed < 0:
        palette_idx = max(speed, min_speed)
        palette_idx = palette_idx / min_speed
        palette_idx = int(palette_idx * (len(neg_speed_palette) - 1))
        return neg_speed_palette[palette_idx]


def get_percentage_color(percentage):
    percentage = min(100, percentage)
    percentage = max(0, percentage)
    return percentage_palette[int(percentage)]


def setup(client):
    client.add_cog(Progress(client))
