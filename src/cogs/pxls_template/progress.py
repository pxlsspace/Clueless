import disnake
import pandas as pd
from PIL import Image
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from disnake.ext import commands

from main import tracked_templates
from utils.discord_utils import Confirm, format_number, image_to_file, UserConverter
from utils.pxls.template_manager import Combo, get_template_from_url, make_before_after_gif, parse_template
from utils.setup import db_templates, db_users
from utils.timezoneslib import get_timezone
from utils.utils import make_progress_bar
from utils.time_converter import round_minutes_down, str_to_td, td_format, format_datetime
from utils.table_to_image import table_to_image
from utils.arguments_parser import MyParser
from utils.plot_utils import get_theme, get_gradient_palette
from cogs.pxls.speed import get_grouped_graph, get_stats_graph
from utils.image.image_utils import v_concatenate


class TemplateURL(disnake.ui.View):
    def __init__(self, template_url: str):
        super().__init__()
        self.add_item(disnake.ui.Button(label="Open Template", url=template_url))


async def autocomplete_templates(inter: disnake.AppCmdInter, user_input: str):
    """Get all the public template names."""
    template_names = [t.name for t in tracked_templates.get_all_public_templates()]
    template_names.append("@combo")
    return [temp_name for temp_name in template_names if user_input.lower() in temp_name.lower()][:25]


async def autocomplete_user_templates(inter: disnake.AppCmdInter, user_input: str):
    """Get all the user-owned template names."""
    author_id = inter.author.id
    if author_id == tracked_templates.bot_owner_id:
        return await autocomplete_templates(inter, user_input)
    else:
        template_names = [t.name for t in tracked_templates.get_all_public_templates() if t.owner_id == inter.author.id]
        return [temp_name for temp_name in template_names if user_input.lower() in temp_name.lower()][:25]


class Progress(commands.Cog):
    def __init__(self, client) -> None:
        self.client = client

    @commands.slash_command(name="progress")
    async def _progress(self, inter):
        """Track a template over time."""
        pass

    @commands.group(
        name="progress",
        usage="<check|info|add|list|update|delete|speed>",
        description="Track a template over time.",
        aliases=["prog"],
        invoke_without_command=True,
    )
    async def progress(self, ctx, template=None):
        if template:
            async with ctx.typing():
                await self.check(ctx, template)
        else:
            await ctx.send("Usage: `>progress <check|info|add|list|update|delete|speed>`")

    @_progress.sub_command(name="check")
    async def _check(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
    ):
        """Check the progress of a template.

        Parameters
        ----------
        template: The name or URL of the template you want to check."""
        await inter.response.defer()
        await self.check(inter, template)

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
        if correct_pixels != 0:
            nb_virgin_abuse = template.get_virgin_abuse()
            virgin_abuse_percentage = (nb_virgin_abuse / total_placeable) * 100
        else:
            nb_virgin_abuse = 0
            virgin_abuse_percentage = 0

        embed = disnake.Embed(title="**Progress Check**", color=0x66C5CC)
        embed.set_thumbnail(url="attachment://template_image.png")

        info_text = f"• Title: `{title}`\n"
        if template.name:
            info_text += f"• Name: `{template.name}`\n"

        embed.add_field(name="**Info**", value=info_text, inline=False)

        progress_text = f"• Correct pixels: `{format_number(correct_pixels)}`/`{format_number(total_placeable)}`\n"
        progress_text += f"• Pixels to go: `{format_number(togo_pixels)}`\n"
        progress_text += "• Virgin abuse: `{}` px (`{}%`)\n".format(
            format_number(nb_virgin_abuse),
            format_number(virgin_abuse_percentage),
        )
        progress_text += f"• Progress:\n**|`{bar}`|** `{correct_percentage}%`\n"

        if is_tracked:
            oldest_record = await db_templates.get_template_oldest_progress(template)
            if oldest_record and oldest_record["datetime"]:
                oldest_record_time = oldest_record['datetime']
            else:
                # if there is no data for this template in the db, the starting tracking time is now
                oldest_record_time = datetime.now(timezone.utc)
            owner = self.client.get_user(template.owner_id)
            embed.set_footer(text=f"Owner • {owner}\nTracking Since")
            embed.timestamp = oldest_record_time
        else:
            prefix = ctx.prefix if isinstance(ctx, commands.Context) else "/"
            embed.set_footer(text=f"[Not Tracked]\nUse {prefix}progress add <name> <url> to start tracking.")
        embed.add_field(name="**Current Progress**", value=progress_text, inline=False)
        detemp_file = image_to_file(progress_image, "progress.png", embed)
        template_file = image_to_file(Image.fromarray(template.get_array()), "template_image.png")

        if isinstance(template, Combo):
            # send the template image first and edit the embed with the URL button
            # using the sent image
            m = await ctx.send(files=[template_file, detemp_file], embed=embed)
            if isinstance(ctx, disnake.AppCmdInter):
                m = await ctx.original_message()
            template_image_url = m.embeds[0].thumbnail.url
            template_url = template.generate_url(template_image_url, default_scale=1)
            view = TemplateURL(template_url)
            await m.edit(view=view)
        else:
            view = TemplateURL(template.generate_url(open_on_togo=True))
            await ctx.send(files=[template_file, detemp_file], embed=embed, view=view)

    @_progress.sub_command(name="info")
    async def _info(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
    ):
        """Get some information about a template.

        Parameters
        ----------
        template: The name of the template."""
        await inter.response.defer()
        await self.info(inter, template)

    @progress.command(
        name="info", description="Get some information about a template.", usage="<template>"
    )
    async def p_info(self, ctx, template: str):
        async with ctx.typing():
            await self.info(ctx, template)

    async def info(self, ctx, template_name):
        # get the template
        try:
            template = tracked_templates.get_template(template_name)
        except Exception as e:
            return await ctx.send(f":x: {e}")
        if template is None:
            return await ctx.send(f"No template named `{template_name}` found.")

        # INFO #
        oldest_record = await db_templates.get_template_oldest_progress(template)
        if oldest_record and oldest_record["datetime"]:
            oldest_record_time = oldest_record['datetime'].replace(tzinfo=timezone.utc)
            oldest_record_time_str = format_datetime(oldest_record_time, "R")
        else:
            oldest_record_time_str = "`< 5 minutes ago`"
        info_text = f"• Title: `{template.title or 'N/A'}`\n"
        info_text += f"• Name: `{template.name}`\n"
        info_text += f"• Owner: <@{template.owner_id}>\n"
        info_text += f"• Started tracking: {oldest_record_time_str}\n"

        # PROGRESS #
        # get the current template progress stats
        total_placeable = template.total_placeable
        correct_pixels = template.update_progress()
        correct_percentage = (correct_pixels / total_placeable) * 100
        togo_pixels = total_placeable - correct_pixels
        if correct_pixels != 0:
            nb_virgin_abuse = template.get_virgin_abuse()
            virgin_abuse_percentage = (nb_virgin_abuse / total_placeable) * 100
        else:
            nb_virgin_abuse = 0
            virgin_abuse_percentage = 0

        progress_text = "• Correct pixels: `{}`/`{}`\n".format(
            format_number(int(correct_pixels)),
            format_number(int(total_placeable)),
        )
        progress_text += f"• Pixels to go: `{format_number(int(togo_pixels))}`\n"
        progress_text += "• Virgin abuse: `{}` px (`{}%`)\n".format(
            format_number(nb_virgin_abuse),
            format_number(virgin_abuse_percentage),
        )
        progress_text += "• Progress:\n**|`{}`|** `{}%`\n".format(
            make_progress_bar(correct_percentage),
            format_number(correct_percentage),
        )
        eta = await template.get_eta()
        progress_text += f"• ETA: `{eta or 'N/A'}`\n"

        # ACTIVITY #
        timeframes = [{"minutes": 5}, {"hours": 1}, {"hours": 6}, {"days": 1}, {"days": 7}, {"days": 9999}]
        timeframe_names = ["5 minutes", "hour", "6 hours", "day", "week"]
        now = round_minutes_down(datetime.utcnow(), 5)
        last_progress_dt, last_progress = await template.get_progress_at(now)
        activity_text = ""
        for i, tf in enumerate(timeframes):
            td = timedelta(**tf)
            tf_datetime, tf_progress = await template.get_progress_at(now - td)
            if tf_progress is None or last_progress is None:
                delta_progress = "`N/A`"
            else:
                delta_progress = last_progress - tf_progress
            if i != len(timeframes) - 1:
                activity_text += "• Last {}: `{}` px\n".format(
                    timeframe_names[i],
                    format_number(delta_progress),
                )
            else:
                delta_time = last_progress_dt - tf_datetime
                if delta_time != timedelta(0):
                    speed_px_d = delta_progress / (delta_time / timedelta(days=1))
                    speed_px_h = delta_progress / (delta_time / timedelta(hours=1))
                    activity_text += "**Average speed**:\n• `{}` px/day\n• `{}` px/hour\n".format(
                        format_number(speed_px_d),
                        format_number(speed_px_h),
                    )
                else:
                    activity_text += "• Average speed: `N/A`\n"

        if last_progress:
            last_updated = format_datetime(last_progress_dt, "R")
        else:
            last_updated = "-"
        activity_text += f"\nLast Updated: {last_updated}"

        embed = disnake.Embed(title=f"Template info for `{template.name}`", color=0x66C5CC)
        embed.add_field(name="**Information**", value=info_text, inline=False)
        embed.add_field(name="**Progress**", value=progress_text, inline=False)
        embed.add_field(name="**Recent Activity**", value=activity_text, inline=False)
        template_file = image_to_file(Image.fromarray(template.get_array()), "template_image.png")
        embed.set_thumbnail(url="attachment://template_image.png")

        if template.url and not isinstance(template, Combo):
            view = TemplateURL(template.generate_url(open_on_togo=True))
            await ctx.send(embed=embed, view=view, file=template_file)
        else:
            m = await ctx.send(file=template_file, embed=embed)
            if isinstance(ctx, disnake.AppCmdInter):
                m = await ctx.original_message()
            template_image_url = m.embeds[0].thumbnail.url
            template_url = template.generate_url(template_image_url, default_scale=1)
            view = TemplateURL(template_url)
            await m.edit(view=view)

    @_progress.sub_command(name="add")
    async def _add(self, inter: disnake.AppCmdInter, name: str, url: str):
        """Add a template to the tracker.

        Parameters
        ----------
        name: The name of the template.
        url: The URL of the template."""
        await inter.response.defer()
        await self.add(inter, name, url)

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
        correct_pixels = template.update_progress()
        try:
            await tracked_templates.save(template, name, ctx.author)
        except ValueError as e:
            return await ctx.send(f":x: {e}")

        # Send template infos

        correct_percentage = format_number((correct_pixels / template.total_placeable) * 100)
        total_placeable = format_number(int(template.total_placeable))
        correct_pixels = format_number(int(correct_pixels))
        total_pixels = format_number(int(template.total_size))

        embed = disnake.Embed(title=f"✅ Template `{name}` added to the tracker.", color=0x66C5CC)
        embed.description = f"**Title**: {template.title or '`N/A`'}\n"
        embed.description += f"[Template link]({template.url})\n"
        embed.description += f"**Size**: {total_pixels} pixels ({template.width}x{template.height})\n"
        embed.description += f"**Coordinates**: ({template.ox}, {template.oy})\n"
        embed.description += f"**Progress**: {correct_percentage}% done ({correct_pixels}/{total_placeable})\n"

        detemp_file = image_to_file(Image.fromarray(template.get_array()), "detemplatize.png", embed)
        await ctx.send(file=detemp_file, embed=embed)

    sort_options = ["Name", "Size", "Correct", "To Go", "Percentage", "px/h (last 1h)", "px/h (last 6h)", "px/h (last 1d)", "px/h (last 7d)", "ETA"]
    Sort = commands.option_enum({option: i for i, option in enumerate(sort_options)})

    @_progress.sub_command(name="list")
    async def _list(
        self,
        inter: disnake.AppCmdInter,
        sort: Sort = None
    ):
        """Show all the public tracked templates.

        Parameters
        ----------
        sort: Sort the table by the chosen column. (default: px/h (last 1h))"""
        await inter.response.defer()
        await self.list(inter, sort)

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
        sort_options = ["name", "size", "correct", "togo", "%", "last1h", "last6h", "last1d", "last7d", "eta"]

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

        titles = ["Name", "Size", "Correct", "To Go", "%", "px/h (last 1h)", "px/h (last 6h)", "px/h (last 1d)", "px/h (last 7d)", "ETA"]
        if sort is None:
            sort = 5
        # make the embed base
        embed = disnake.Embed(title="Tracked Templates", color=0x66C5CC)
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
        public_tracked_templates.append(tracked_templates.combo)
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
            # ETA
            speed_last_7d = values[-1]
            if togo != "N/A" and speed_last_7d != "N/A":
                if togo == 0:
                    eta = 0
                    line_colors.append(get_eta_color(0))
                elif speed_last_7d <= 0:
                    eta = 999999
                    line_colors.append("#b11206")
                else:
                    eta = togo / speed_last_7d
                    line_colors.append(get_eta_color(eta))
            else:
                eta = "N/A"
                line_colors.append(None)

            table.append([name, total, current_progress, togo, percentage] + values + [eta] + [line_colors])

        # sort the table
        if sort == 0:
            # sorting by name: keep normal order and ignore case
            reverse = False
            key = lambda x: (x[sort] is None or isinstance(x[sort], str), x[sort].lower())  # noqa: E731

        elif sort == len(titles) - 1:
            # sorting by ETA: keep normal order
            reverse = False
            key = lambda x: (x[sort] is None or isinstance(x[sort], str), x[sort])  # noqa: E731
        else:
            # sorting by a number: reverse the order and ignore strings
            reverse = True
            key = lambda x: (x[sort] is not None and not(isinstance(x[sort], str)), x[sort])  # noqa: E731
        table.sort(key=key, reverse=reverse)
        table_data = [line[:-1] for line in table]
        table_colors = [line[-1] for line in table]
        # format the data
        for i, row in enumerate(table_data):
            if row[-1] is not None and row[-1] != "N/A":
                if row[-1] >= 999999:
                    row[-1] = "Never."
                elif row[-1] <= 0:
                    row[-1] = "-Done-"
                else:
                    row[-1] = td_format(
                        timedelta(hours=row[-1]),
                        hide_seconds=True,
                        max_unit="day",
                        short_format=True,
                    )
            table_data[i] = [format_number(c) for c in row]
        # make the table image
        discord_user = await db_users.get_discord_user(ctx.author.id)
        current_user_theme = discord_user["color"] or "default"
        theme = deepcopy(get_theme(current_user_theme))
        bg_colors = None
        if theme.name == "light":
            bg_colors = table_colors
            table_colors = None
        theme.outline_dark = False
        table_image = table_to_image(
            table_data,
            titles,
            colors=table_colors,
            bg_colors=bg_colors,
            theme=theme,
            alternate_bg=True,
            scale=3,
        )
        table_file = image_to_file(table_image, "progress.png", embed=embed)
        await ctx.send(embed=embed, file=table_file)

    @_progress.sub_command(name="update")
    async def _update(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_user_templates),
        new_url: str = commands.Param(name="new-url", default=None),
        new_name: str = commands.Param(name="new-name", default=None),
        new_owner: disnake.User = commands.Param(name="new-owner", default=None),
    ):
        """Update a template in the tracker.

        Parameters
        ----------
        template: The current name of the template you want to update.
        new_url: The new URL of the template.
        new_name: The new name of the template.
        new_owner: The new owner of the template."""
        await inter.response.defer()
        await self.update(inter, template, new_url, new_name, new_owner)

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
            await self.update(ctx, current_name, new_owner=new_user)

    async def update(self, ctx, current_name, new_url=None, new_name=None, new_owner=None):
        try:
            old_temp, new_temp = await tracked_templates.update_template(
                current_name,
                ctx.author,
                new_url, new_name,
                new_owner,
            )
        except ValueError as e:
            return await ctx.send(f":x: {e}")
        embed = disnake.Embed(title=f"**✅ Template {old_temp.name} Updated**", color=0x66C5CC)

        # Show name update
        if new_name is not None:
            embed.add_field(name="Name Changed", value=f"`{old_temp.name}` → `{new_temp.name}`", inline=False)

        # Show owner update
        if new_owner is not None:
            embed.add_field(name="Ownership transfered", value=f"<@{old_temp.owner_id}> → <@{new_temp.owner_id}>", inline=False)

        # Show all the template info updated
        if new_url is not None:
            info = "__**Info**__\n"
            # title
            if old_temp.title != new_temp.title:
                info += f"• **Title**: `{old_temp.title}` → `{new_temp.title}`\n"
            else:
                info += f"• **Title**: `{new_temp.title}` *(unchanged)*\n"
            # url
            info += f"• **URL**: [[old]]({old_temp.url}) → [[new]]({new_temp.url})\n"
            # coords
            old_coords = (old_temp.ox, old_temp.oy)
            new_coords = (new_temp.ox, new_temp.oy)
            if old_coords != new_coords:
                info += "• **Coords**: {} → {}\n".format(old_coords, new_coords)
            else:
                info += f"• **Coords**: ({new_temp.ox}, {new_temp.oy}) *(unchanged)*\n"
            # dimensions
            old_dims = f"({old_temp.width}x{old_temp.height})"
            new_dims = f"({new_temp.width}x{new_temp.height})"
            if old_dims != new_dims:
                info += "• **Dimensions**: {} → {}\n".format(old_dims, new_dims)
            else:
                info += f"• **Dimensions**: {new_dims} *(unchanged)*\n"
            # size
            old_size = old_temp.total_placeable
            new_size = new_temp.total_placeable
            if old_size != new_size:
                diff_size = new_size - old_size
                info += "• **Size**: {} → {} `[{}{}]`\n".format(
                    format_number(old_size),
                    format_number(new_size),
                    "+" if diff_size > 0 else "",
                    format_number(diff_size),
                )
            else:
                info += f"• **Size**: {format_number(new_size)} *(unchanged)*\n"

            # progress
            progress = "\n__**Progress**__\n"
            new_prog = new_temp.update_progress()
            old_prog = old_temp.update_progress()
            if old_prog != new_prog:
                diff_prog = new_prog - old_prog
                progress += "• **Correct Pixels**: {} → {} `[{}{}]`\n".format(
                    format_number(old_prog),
                    format_number(new_prog),
                    "+" if diff_prog > 0 else "",
                    format_number(diff_prog),
                )
            else:
                progress += f"• **Correct Pixels**: {format_number(new_prog)} *(unchanged)*\n"
            old_togo = old_temp.total_placeable - old_prog
            new_togo = new_temp.total_placeable - new_prog
            # to go
            if old_togo != new_togo:
                diff_togo = new_togo - old_togo
                progress += "• **Pixels to go**: {} → {} `[{}{}]`\n".format(
                    format_number(old_togo),
                    format_number(new_togo),
                    "+" if diff_togo > 0 else "",
                    format_number(diff_togo),

                )
            else:
                progress += f"• **Pixels to go**: {format_number(new_togo)} *(unchanged)*\n"
            # percentage
            old_percentage = old_prog / old_temp.total_placeable
            new_percentage = new_prog / new_temp.total_placeable
            if old_percentage != new_percentage:
                diff_percentage = new_percentage - old_percentage
                progress += "• **Percentage**: {}% → {}% `[{}{}%]`\n".format(
                    format_number(old_percentage * 100),
                    format_number(new_percentage * 100),
                    "+" if diff_percentage > 0 else "",
                    format_number(diff_percentage * 100),
                )
            else:
                progress += f"• **Percentage**: {format_number(new_percentage)}% *(unchanged)*\n"
            progress += "\n__**Image Difference**__\n"
            # make the image
            try:
                diff_gif = await self.client.loop.run_in_executor(
                    None, make_before_after_gif, old_temp, new_temp
                )
                filename = "diff.gif"
                files = [disnake.File(fp=diff_gif, filename=filename)]
                embed.set_image(url=f"attachment://{filename}")
            except Exception:
                progress += "**[An error occured while generating the diff GIF image.]**\n"
                files = []
            embed.add_field(name="URL Changed", value=info + progress)
        else:
            files = []

        return await ctx.send(embed=embed, files=files)

    @_progress.sub_command(name="delete")
    async def _delete(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_user_templates),
    ):
        """Delete a template and all its stats from the tracker.

        Parameters
        ----------
        template: The name of the template you want to delete."""
        await inter.response.defer()
        await self.delete(inter, template)

    @progress.command(
        name="delete",
        description="Delete a template and all its stats from the tracker.",
        usage="<template>",
        aliases=["remove", "del"],
    )
    async def p_delete(self, ctx, template: str):
        async with ctx.typing():
            await self.delete(ctx, template)

    async def delete(self, ctx, template_name):
        try:
            temp = tracked_templates.get_template(template_name, ctx.author.id, False)
            if not temp:
                raise ValueError(f"No template named `{template_name}` found.")
            if temp.owner_id != ctx.author.id and ctx.author.id != tracked_templates.bot_owner_id:
                raise ValueError("You cannot delete a template that you don't own.")
            if isinstance(temp, Combo):
                raise ValueError("You cannot delete the combo.")
        except Exception as e:
            return await ctx.send(f":x: {e}")

        confirm_title = f"⚠️ Are you sure you want to DELETE `{temp.name}` from the tracker?"
        confirm_text = "This is **IRREVERSIBLE**!\nThis template and all its stats will be **FOREVER LOST** if you proceed."
        confirm_embed = disnake.Embed(title=confirm_title, description=confirm_text, color=0xffcc00)
        confirm_view = Confirm(ctx.author)
        confirm_view.message = await ctx.send(embed=confirm_embed, view=confirm_view)
        if isinstance(ctx, disnake.AppCmdInter):
            confirm_view.message = await ctx.original_message()

        await confirm_view.wait()

        if not confirm_view.value:
            if confirm_view.value is None:
                title = "Operation Timed out"
            else:
                title = "Operation Cancelled"
            embed = disnake.Embed(
                title=title,
                description=f"The template `{temp.name}` was **not** deleted.",
                color=0x66C5CC,
            )
        else:
            try:
                deleted_temp = await tracked_templates.delete_template(
                    template_name,
                    ctx.author,
                    False,
                )
            except Exception as e:
                return await ctx.send(f":x: {e}")
            embed = disnake.Embed(
                title="✅ Template Deleted",
                description=f"The template `{deleted_temp.name}` and all its stats were successfully deleted.",
                color=0x3ba55d,
            )

        return await confirm_view.message.edit(embed=embed)

    @_progress.sub_command(name="speed")
    async def _speed(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
        last: str = None,
        groupby: str = commands.Param(default=None, choices=["5min", "hour", "day"])
    ):
        """Check the speed graph of a tracked template.

        Parameters
        ----------
        template: The name of the template you want to check.
        last: Show the progress in the last x week/day/hour/minute. (format: ?w?d?h?m)
        groupby: Show a bar chart for each 5 min interval, hour or day."""
        await inter.response.defer()
        await self.speed(inter, template, last, groupby)

    @progress.command(
        name="speed",
        description="Check the speed graph of a tracked template.",
        usage="<template> [-last ?w?d?h?m] [-groupby 5min]",
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
                oldest_time = dates.pop(0).astimezone(timezone.utc).replace(tzinfo=None)
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
        embed = disnake.Embed(title="**Template Speed**", color=0x66C5CC)
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
percentage_palette = get_gradient_palette(["#e21000", "#fca80e", "#fff491", "#beff40", "#31a117"], 101)


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


def get_eta_color(eta_hours, max_days=40):
    eta_idx = max(0, min(eta_hours / 24, max_days))
    eta_idx = 1 - (eta_idx / max_days)
    eta_idx = int(eta_idx * (len(percentage_palette) - 1))
    return percentage_palette[eta_idx]


def setup(client):
    client.add_cog(Progress(client))
