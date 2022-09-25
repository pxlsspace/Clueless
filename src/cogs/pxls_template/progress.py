import asyncio
import re
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO

import aiohttp
import disnake
import numpy as np
import pandas as pd
from disnake.ext import commands
from PIL import Image

from cogs.pxls.speed import get_grouped_graph, get_stats_graph
from main import tracked_templates
from utils.arguments_parser import MyParser
from utils.discord_utils import (
    AddTemplateView,
    Confirm,
    DropdownView,
    MoreInfoView,
    UserConverter,
    autocomplete_templates,
    autocomplete_user_templates,
    format_number,
    get_image_url,
    image_to_file,
)
from utils.image.image_utils import find_upscale, v_concatenate
from utils.plot_utils import (
    fig2img,
    get_gradient_palette,
    get_theme,
    matplotlib_to_plotly,
)
from utils.pxls.template import get_rgba_palette, reduce
from utils.pxls.template_manager import (
    Combo,
    get_template_from_url,
    make_before_after_gif,
    parse_template,
)
from utils.setup import db_stats, db_templates, db_users, imgur_app, stats
from utils.table_to_image import table_to_image
from utils.time_converter import (
    format_datetime,
    get_datetimes_from_input,
    round_minutes_down,
    str_to_td,
    td_format,
)
from utils.timezoneslib import get_timezone
from utils.utils import BadResponseError, make_progress_bar, shorten_list


class Progress(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        self.refresh_cooldown = commands.CooldownMapping.from_cooldown(
            1, 10, commands.BucketType.user
        )
        self.timelapse_cd = commands.CooldownMapping.from_cooldown(
            1, 20, commands.BucketType.user
        )

    @commands.slash_command(name="progress")
    async def _progress(self, inter):
        """Track a template over time."""
        pass

    @commands.group(
        name="progress",
        usage="<check|add|list|update|rename|transfer|delete|speed|timelapse|coords>",
        description="Track a template over time.",
        aliases=["prog"],
        invoke_without_command=True,
    )
    async def progress(self, ctx, template=None, display=None):
        if template:
            async with ctx.typing():
                await self.p_check(ctx, template, display)
        else:
            await ctx.send(
                f"Usage: `{ctx.prefix}{self.progress.name} {self.progress.usage}`\n*(Use `{ctx.prefix}help {self.progress.name}` for more information)*"
            )

    display_options = {
        "Default (progress image)": "default",
        "Template": "template",
        "Template (Highlighted)": "hltemplate",
        "Wrong Pixels": "wrong",
        "Wrong Pixels (Highlighted)": "hlwrong",
        "Correct Pixels": "correct",
        "Correct Pixels (Highlighted)": "hlcorrect",
        "Canvas": "canvas",
        "Heatmap": "heatmap",
        "Virginmap": "virginmap",
        "Virginabuse": "virginabuse",
        "None": "none",
    }

    @_progress.sub_command(name="check")
    async def _check(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
        display: str = commands.Param(default="Default", choices=display_options),
    ):
        """Check the progress of a template.

        Parameters
        ----------
        template: The name or URL of the template you want to check.
        display: How to display the template."""
        await inter.response.defer()
        await self.check(inter, template, display)

    @progress.command(
        name="check",
        description="Check the progress of a template.",
        usage="<name|URL> [display option]",
        help="""
        - `<name|URL>`: The name or URL of the template you want to check
        - `[display option]`: How to display the template.

        **Display Options**:
        • `default`: The progress image.
        • `template`: The template image.
        • `hltemplate`: The template image over the canvas.
        • `wrong`: Only the wrong pixels.
        • `hlwrong`: Wrong pixels highlighted over the template.
        • `canvas`: The canvas in the template area.
        • `heatmap`: The heatmap in the template area.
        • `virginmap`: The virginmap in the template area.
        • `virginabuse`: The pixels that are both correct and virgin.
        • `none`: No image.""",
    )
    async def p_check(self, ctx, template, display=None):
        if display and display.lower() not in self.display_options.values():
            options = " ".join([f"`{o}`" for o in self.display_options.values()])
            err_msg = f":x: Invalid display option '{display}' (choose from {options})"
            return await ctx.send(err_msg)
        async with ctx.typing():
            await self.check(ctx, template, display.lower() if display else None)

    async def check(self, ctx, template_input, display):
        # check if the input is an URL or template name
        try:
            check_values = await self.make_check_embed(ctx, template_input, display)
        except ValueError as e:
            return await ctx.send(
                embed=disnake.Embed(color=disnake.Color.red(), description=f":x: {e}")
            )
        if check_values is None:
            return
        embed, files, view = check_values
        m = await ctx.send(files=files, embed=embed, view=view)
        if isinstance(ctx, disnake.AppCmdInter):
            ctx.send
            m = await ctx.original_message()
        if view:
            view.message = m

    async def make_check_embed(self, ctx, template_input, display, state=0):
        if parse_template(template_input) is not None:
            template = await get_template_from_url(template_input)

            # check if we have a tracked template with the same image and coords
            template_with_same_image = tracked_templates.check_duplicate_template(
                template
            )
            if template_with_same_image:
                template = template_with_same_image
                is_tracked = True
            else:
                is_tracked = False
        else:
            template = tracked_templates.get_template(template_input, None, False)
            if template is None:
                raise ValueError(
                    f"There is no template with the name `{template_input}` in the tracker."
                )
            is_tracked = True

        # get the current template progress stats
        title = template.title or "`N/A`"
        total_placeable = template.total_placeable
        correct_pixels = template.update_progress()
        if total_placeable == 0:
            raise ValueError(
                ":x: The template seems to be outside the canvas, make sure it's correctly positioned."
            )
        correct_percentage = round((correct_pixels / total_placeable) * 100, 2)
        togo_pixels = total_placeable - correct_pixels

        # get the image to display
        if display == "template":
            progress_image = Image.fromarray(template.get_array())
        elif display == "hltemplate":
            progress_image = await template.get_preview_image(
                crop_to_template=False, opacity=0.5
            )
        elif display == "wrong":
            wrong_pixels = template.palettized_array.copy()
            wrong_pixels[~template.get_wrong_pixels_mask()] = 255
            progress_image = Image.fromarray(stats.palettize_array(wrong_pixels))
        elif display == "hlwrong":
            wrong_pixels = template.palettized_array.copy()
            wrong_pixels[~template.get_wrong_pixels_mask()] = 255
            wrong_pixels = stats.palettize_array(wrong_pixels)
            progress_image = await template.get_preview_image(wrong_pixels)
        elif display == "correct":
            correct_pixels_array = template.palettized_array.copy()
            correct_pixels_array[~template.placed_mask] = 255
            progress_image = Image.fromarray(stats.palettize_array(correct_pixels_array))
        elif display == "hlcorrect":
            correct_pixels_array = template.palettized_array.copy()
            correct_pixels_array[~template.placed_mask] = 255
            correct_pixels_array = stats.palettize_array(correct_pixels_array)
            progress_image = await template.get_preview_image(correct_pixels_array)
        elif display in ["canvas", "virginmap"]:
            if display == "canvas":
                board = await stats.get_placable_board()
                palette = None
            elif display == "virginmap":
                board = stats.virginmap_array.copy()
                board[board == 255] = 1
                palette = ["#000000", "#00FF00"]
            cropped_board = template.crop_array_to_template(board)
            cropped_board[~template.placeable_mask] = 255
            progress_image = Image.fromarray(
                stats.palettize_array(cropped_board, palette)
            )
        elif display == "heatmap":
            heatmap = await stats.fetch_heatmap()
            heatmap = 255 - heatmap
            palette = matplotlib_to_plotly("plasma_r", 255)
            cropped_heatmap = template.crop_array_to_template(heatmap)
            cropped_heatmap[~template.placeable_mask] = 255
            cropped_heatmap = stats.palettize_array(cropped_heatmap, palette)
            progress_image = await template.get_preview_image(cropped_heatmap)
        elif display == "virginabuse":
            template_virginmap = template.crop_array_to_template(stats.virginmap_array)
            board = np.logical_and(template_virginmap, template.placed_mask)
            board.dtype = np.uint8
            board[~template.placeable_mask] = 255
            palette = ["#000000", "#00FF00"]
            progress_image = Image.fromarray(stats.palettize_array(board, palette))
        elif display == "none":
            pass
        else:
            display = "default"
            progress_image = template.get_progress_image()
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
        if display != "none":
            footer_text = f"Displaying: {[name for name,val in self.display_options.items() if val == display][0]}"
        else:
            footer_text = ""
        if is_tracked:
            footer_text += "\nLast updated"
            embed.timestamp = disnake.utils.utcnow()

        # INFO #
        info_text = f"• Title: `{title}`\n"
        if template.name:
            info_text += f"• Name: `{template.name}`\n"

        # TRACKING INFO #
        if is_tracked:
            oldest_record = await db_templates.get_template_oldest_progress(template)
            if oldest_record and oldest_record["datetime"]:
                oldest_record_time_str = format_datetime(oldest_record["datetime"], "R")

            else:
                oldest_record_time_str = "`< 5 min ago`"

            info_text += f"• Owner: <@{template.owner_id}>\n"
            info_text += f"• Started tracking: {oldest_record_time_str}"
        else:
            if not template.stylized_url.startswith("data:image"):
                footer_text += "\nThis template is not in the tracker.\nClick on [Add To Tracker] to add it directly."

        embed.set_footer(text=footer_text)
        embed.add_field(name="**Info**", value=info_text, inline=True)

        # PROGRESS #
        progress_text = f"• Correct pixels: `{format_number(correct_pixels)}`/`{format_number(total_placeable)}`\n"
        progress_text += f"• Pixels to go: `{format_number(togo_pixels)}`\n"
        progress_text += "• Virgin abuse: `{}` px (`{}%`)\n".format(
            format_number(nb_virgin_abuse),
            format_number(virgin_abuse_percentage),
        )
        progress_text += f"• Progress:\n**|`{bar}`|** `{correct_percentage}%`\n"
        if is_tracked:
            eta, eta_speed = await template.get_eta()
            if eta == "done" and nb_virgin_abuse == 0:
                clap_emoji = "<a:HyperClapCat:976892768209219624>"
                progress_text += f"• ETA: {clap_emoji} `Done!` {clap_emoji}\n"
            elif eta == "done":
                clap_emoji = "<a:clapcat:976892767705903155>"
                progress_text += f"• ETA: {clap_emoji} `Done!` {clap_emoji}\n"
            else:
                progress_text += "• ETA: `{}`{}\n".format(
                    eta or "N/A",
                    f" *(at `{format_number(eta_speed)}` px/h)*" if eta_speed else "",
                )

        if togo_pixels == 0:
            embed.color = 0x1EC31E

        embed.add_field(name="**Current Progress**", value=progress_text, inline=False)

        # ACTIVITY #
        activity_text = ""
        if is_tracked:
            timeframes = [
                {"minutes": 5},
                {"hours": 1},
                {"hours": 6},
                {"days": 1},
                {"days": 7},
                {"days": 9999},
            ]
            timeframe_names = ["5 minutes", "hour", "6 hours", "day", "week"]
            now = round_minutes_down(datetime.utcnow(), 5)
            last_progress_dt, last_progress = await template.get_progress_at(now)
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
                    if tf_progress is None or last_progress is None:
                        activity_text += "• Average speed: `N/A`\n"
                    else:
                        delta_time = last_progress_dt - tf_datetime
                        if delta_time != timedelta(0):
                            speed_px_d = delta_progress / (delta_time / timedelta(days=1))
                            speed_px_h = delta_progress / (
                                delta_time / timedelta(hours=1)
                            )
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
            activity_text += f"\nStats Updated: {last_updated}"

        files = []
        if display != "none":
            progress_file = await image_to_file(progress_image, f"{display}.png", embed)
            files.append(progress_file)
        template_file = await image_to_file(
            Image.fromarray(template.get_array()), "template_image.png"
        )
        files.append(template_file)

        embed_expanded = embed.copy()
        # this is necessary because embed.copy() keeps the same fields ..
        embed_expanded._fields = embed._fields.copy()
        embed_expanded.add_field(
            name="**Recent Activity**", value=activity_text, inline=False
        )

        if isinstance(template, Combo):
            # send the template image first and edit the embed with the URL button
            # using the sent image
            m = await ctx.send(files=files, embed=embed)
            if isinstance(ctx, disnake.AppCmdInter):
                m = await ctx.original_message()
            template_image_url = get_image_url(m.embeds[0].thumbnail)
            template_url = template.generate_url(template_image_url, default_scale=1)
            view = MoreInfoView(
                ctx.author,
                embed,
                embed_expanded,
                template_url,
                self.speed,
                template.name,
                oldest_record["datetime"] or datetime.utcnow(),
                add_refresh=False,
            )
            view.message = m
            await m.edit(view=view)
            return None
        else:
            template_url = template.generate_url(open_on_togo=True)
            if is_tracked:
                view = MoreInfoView(
                    ctx.author,
                    embed,
                    embed_expanded,
                    template_url,
                    self.speed,
                    template.name,
                    oldest_record["datetime"] or datetime.utcnow(),
                    add_refresh=True,
                    display=display,
                    state=state,
                )
            else:
                if template.stylized_url.startswith("data:image"):
                    view = (
                        None
                        if isinstance(ctx, commands.Context)
                        else disnake.utils.MISSING
                    )
                else:
                    view = AddTemplateView(ctx.author, template_url, self.add)
            return embed if state == 0 else embed_expanded, files, view

    @commands.Cog.listener()
    async def on_button_click(self, inter: disnake.MessageInteraction):
        """Handle what to do when the "add key" or "list keys" button is pressed."""
        custom_id = inter.component.custom_id
        parsed_id = custom_id.split(":")
        if parsed_id[0] != "prog_refresh":
            return

        # check the author
        template_name, display, state, button_author_id = parsed_id[1].split(",")
        if inter.author.id != int(button_author_id):
            return await inter.send(
                embed=disnake.Embed(
                    title="This isn't your command!",
                    color=0xFF3621,
                    description="You cannot interact with a command you did not call.",
                ),
                ephemeral=True,
            )

        # check the cooldown
        retry_after = self.refresh_cooldown.update_rate_limit(inter)
        if retry_after:
            # rate limited
            embed = disnake.Embed(
                title="You're doing this too quick!",
                description=f"You are on cooldown for refresh buttons, try again in **{round(retry_after,2)}s**.",
                color=0xFF3621,
            )
            return await inter.send(ephemeral=True, embed=embed)

        # get the new embed, files, view
        await inter.response.defer()
        try:
            check_values = await self.make_check_embed(
                inter, template_name, display, int(state)
            )
        except ValueError:
            check_values = None

        if check_values is None:
            return await inter.send(
                embed=disnake.Embed(
                    color=disnake.Color.red(),
                    description=":x: An error occurred, couldn't refresh the progress.",
                ),
                ephemeral=True,
            )
        embed, files, view = check_values
        m = await inter.edit_original_message(embed=embed, files=files, view=view)
        view.message = m
        self.refresh_cooldown.get_bucket(inter).reset()
        self.refresh_cooldown.update_rate_limit(inter)

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

    @staticmethod
    async def add(ctx, name, url):
        try:
            template = await get_template_from_url(url)
        except ValueError as e:
            await ctx.send(f":x: {e}")
            return False

        if template.total_placeable == 0:
            await ctx.send(
                ":x: The template seems to be outside the canvas, make sure it's correctly positioned."
            )
            return False
        correct_pixels = template.update_progress()
        try:
            await tracked_templates.save(template, name, ctx.author)
        except ValueError as e:
            await ctx.send(f":x: {e}")
            return False

        # Send template infos

        correct_percentage = format_number(
            (correct_pixels / template.total_placeable) * 100
        )
        total_placeable = format_number(int(template.total_placeable))
        correct_pixels = format_number(int(correct_pixels))
        total_pixels = format_number(int(template.total_size))

        embed = disnake.Embed(
            title=f"✅ Template `{name}` added to the tracker.", color=0x66C5CC
        )
        embed.description = f"**Title**: {template.title or '`N/A`'}\n"
        embed.description += f"[Template link]({template.url})\n"
        embed.description += (
            f"**Size**: {total_pixels} pixels ({template.width}x{template.height})\n"
        )
        embed.description += f"**Coordinates**: ({template.ox}, {template.oy})\n"
        embed.description += f"**Progress**: {correct_percentage}% done ({correct_pixels}/{total_placeable})\n"

        detemp_file = await image_to_file(
            Image.fromarray(template.get_array()), "detemplatize.png", embed
        )
        await ctx.send(file=detemp_file, embed=embed)
        return True

    sort_options = [
        ("Name", "name"),
        ("Size", "size"),
        ("Correct", "correct"),
        ("To Go", "togo"),
        ("%", "%"),
        ("px/h (last 1h)", "last1h"),
        ("px/h (last 6h)", "last6h"),
        ("px/h (last 1d)", "last1d"),
        ("px/h (last 7d)", "last7d"),
        ("ETA", "eta"),
    ]
    Sort = commands.option_enum({option[0]: i for i, option in enumerate(sort_options)})
    filter_options = {"Not Done": "notdone", "Done": "done", "Mine": "mine"}

    def autocomplete_filter(inter: disnake.AppCmdInter, user_input: str):
        user_input = user_input.split("+")
        to_search = user_input[-1]
        rest = user_input[:-1]
        filters = ["notdone", "done", "mine"]
        for r in rest:
            if r not in filters:
                return []
        rest = "+".join(rest)
        best_matches = [
            filter for filter in filters if to_search.lower() in filter.lower()
        ][:25]
        return [rest + ("+" if rest else "") + best_match for best_match in best_matches]

    @_progress.sub_command(name="list")
    async def _list(
        self,
        inter: disnake.AppCmdInter,
        sort: Sort = None,
        filter: str = commands.Param(default=None, autocomplete=autocomplete_filter),
        coords: str = None,
        temp_per_page: int = commands.Param(
            default=15, name="templates-per-page", gt=5, lt=40
        ),
    ):
        """Show all the public tracked templates.

        Parameters
        ----------
        sort: Sort the table by the chosen column. (default: px/h (last 1h))
        filter: Apply a filter to only display the chosen templates. (format: filter1+filter2+ ...)
        coords: To only see templates at coordinates. (format: x y or pxls link)
        temp_per_page: The number of templates displayed in a page between 5 and 40. (default: 15)"""
        await inter.response.defer()
        await self.list(inter, sort, filter, coords, temp_per_page)

    @progress.command(
        name="list",
        description="Show all the public tracked templates.",
        aliases=["ls"],
        usage="[-sort <column>] [-coords x y] [-tpp <number>] [-filter <filter1+filter2+...>]",
        help="""
        `[-sort <column>]`: Sort the table by the chosen column.
        `[-coords x y]`: To only see templates at coordinates (format: x y or pxls link).
        `[-tpp <number>]`: The number of templates to display in a page between 5 and 40. (default: 15).
        `[-filter <filter1+filter2+...>]`: Apply a filter to only display the chosen templates.
        The available filters are:
        - `notdone`: to only show the templates not done
        - `done`: to only show the templates done
        - `mine`: to only show templates that you own
        e.g. `>progress list -filter mine+notdone` will show all your templates that are not done.
        """,
    )
    async def p_list(self, ctx, *args):
        parser = MyParser(add_help=False)
        options_dict = {option[1]: i for i, option in enumerate(self.sort_options)}
        parser.add_argument(
            "-sort", "-s", choices=list(options_dict.keys()), required=False
        )
        parser.add_argument("-filter", "-f", type=str, required=False)
        parser.add_argument("-coords", "-c", nargs="+", required=False)
        parser.add_argument(
            "-tpp", "-templates-per-page", type=int, required=False, default=15
        )

        try:
            parsed_args = parser.parse_args(args)
        except Exception as error:
            return await ctx.send(f"❌ {error}")
        sort = options_dict.get(parsed_args.sort) if parsed_args.sort else None
        coords = " ".join(parsed_args.coords) if parsed_args.coords else None
        if parsed_args.tpp < 5 or parsed_args.tpp > 40:
            return await ctx.send(
                ":x: The number of templates per page must be between 5 and 40."
            )
        async with ctx.typing():
            await self.list(ctx, sort, parsed_args.filter, coords, parsed_args.tpp)

    async def list(
        self,
        ctx,
        sort: int = None,
        filters: str = None,
        coords: str = None,
        temp_per_page=15,
    ):
        if tracked_templates.is_loading:
            return await ctx.send(":x: Templates are loading, try again later.")
        public_tracked_templates = tracked_templates.get_all_public_templates()
        if len(public_tracked_templates) == 0:
            return await ctx.send("No templates tracked :'(")

        titles = [t[0] for t in self.sort_options]
        if sort is None:
            sort = 5

        # check that the filters are all valid
        if filters:
            filters = filters.lower().split("+")
            for filter in filters:
                if filter not in self.filter_options.values():
                    msg = ":x: Invalid filter choice '{}' (choose from {}).".format(
                        filter,
                        ", ".join([f"`{f}`" for f in self.filter_options.values()]),
                    )
                    return await ctx.send(msg)

        # check on the coords
        if coords:
            coords = re.findall(r"-?\d+", coords)
            if len(coords) < 2:
                return await ctx.send(
                    ":x: Invalid coordinates (format: x y or pxls link)."
                )
            coords = coords[:2]
            try:
                coords = [int(c) for c in coords]
            except ValueError:
                return await ctx.send(":x: Coordinates must be integers.")
            x, y = coords
            if (
                x < 0
                or y < 0
                or x > stats.board_array.shape[1]
                or y > stats.board_array.shape[0]
            ):
                return await ctx.send(":x: Coordinates must be inside the canvas.")

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

            # Filters
            if filters:
                if "notdone" in filters and togo == 0:
                    continue
                if "done" in filters and togo != 0:
                    continue
                if "mine" in filters and template.owner_id != ctx.author.id:
                    continue

            # coords filter
            if coords:
                # ignore template if the coords aren't in the placeable area
                if (
                    x < template.ox
                    or y < template.oy
                    or x > template.ox + template.width
                    or y > template.oy + template.height
                ):
                    continue
                if not template.placeable_mask[y - template.oy, x - template.ox]:
                    continue

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

            table.append(
                [name, total, current_progress, togo, percentage]
                + values
                + [eta]
                + [line_colors]
            )

        if len(table) == 0:
            if filters:
                return await ctx.send(":x: No template matches with your filter.")
            if coords:
                return await ctx.send(
                    f":x: There are no tracked templates at the given coordinates ({x}, {y})."
                )

        discord_user = await db_users.get_discord_user(ctx.author.id)
        current_user_theme = discord_user["color"] or "default"
        theme = deepcopy(get_theme(current_user_theme))
        font = discord_user["font"]
        last_updated = await db_templates.get_last_update_time()

        async def make_embeds(table, sort, temp_per_page):
            # sort the table
            if sort == 0:
                # sorting by name: keep normal order and ignore case
                reverse = False
                key = lambda x: (
                    x[sort] is None or isinstance(x[sort], str),
                    x[sort].lower(),
                )

            elif sort == len(titles) - 1:
                # sorting by ETA: keep normal order
                reverse = False
                key = lambda x: (
                    x[sort] is None or isinstance(x[sort], str),
                    x[sort],
                )
            else:
                # sorting by a number: reverse the order and ignore strings
                reverse = True
                key = lambda x: (
                    x[sort] is not None and not (isinstance(x[sort], str)),
                    x[sort],
                )
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
            bg_colors = None
            if theme.name == "light":
                bg_colors = table_colors
                table_colors = None
            theme.outline_dark = False

            def split(array, chunks):
                if array is None:
                    return None
                return [array[i : i + chunks] for i in range(0, len(array), chunks)]

            # Split the data to make the pages
            table_data_pages = split(table_data, temp_per_page)
            table_colors_pages = split(table_colors, temp_per_page)
            bg_colors_pages = split(bg_colors, temp_per_page)
            nb_page = len(table_data_pages)
            table_images = []
            for i in range(nb_page):
                table_image = await table_to_image(
                    table_data_pages[i],
                    titles,
                    colors=table_colors_pages[i] if table_colors_pages else None,
                    bg_colors=bg_colors_pages[i] if bg_colors_pages else None,
                    theme=theme,
                    font=font,
                    alternate_bg=True,
                )
                table_images.append(table_image)

            # make the embed base
            embeds = []
            for i in range(nb_page):
                embed = disnake.Embed(title="Tracked Templates", color=0x66C5CC)
                embed.description = f"Sorted By: `{titles[sort]}`\n"
                if filters:
                    filter_str_list = []
                    for filter in filters:
                        if filter == "notdone":
                            filter_str_list.append("`Not Done`")
                        elif filter == "done":
                            filter_str_list.append("`Done`")
                        elif filter == "mine":
                            filter_str_list.append(f"<@{ctx.author.id}>'s templates")
                    embed.description += f"Filter: {' + '.join(filter_str_list)}\n"
                if coords:
                    embed.description += "Coordinates Filter: [`({0}, {1})`](https://pxls.space/#x={0}&y={1}&scale=20)\n".format(
                        x, y
                    )
                embed.description += f"Total Templates: `{len(table)}`"
                if last_updated:
                    if nb_page > 1:
                        embed.set_footer(text=f"Page {i+1}/{nb_page}\nLast Updated")
                    else:
                        embed.set_footer(text="Last Updated")

                    embed.timestamp = last_updated
                embeds.append(embed)
            return embeds, table_images

        class SortDropdown(disnake.ui.Select):
            def __init__(self):
                options = []
                for i, title in enumerate(titles):
                    options.append(
                        disnake.SelectOption(label=title, value=i, default=i == sort)
                    )

                super().__init__(
                    placeholder="Sort the progress list ...",
                    min_values=1,
                    max_values=1,
                    options=options,
                )

            async def callback(self, inter: disnake.MessageInteraction):
                sort_index = int(self.values[0])
                for option in self.options:
                    if int(option.value) == sort_index:
                        option.default = True
                    else:
                        option.default = False
                await inter.response.defer()
                embeds, images = await make_embeds(table, sort_index, temp_per_page)
                await self.view.update_embeds(inter, embeds, images)

        embeds, images = await make_embeds(table, sort, temp_per_page)

        dropdown = SortDropdown()
        dropdown_view = DropdownView(ctx.author, dropdown, embeds, images)
        file = await image_to_file(images[0], "progress.png", embeds[0])
        m = await ctx.send(embed=embeds[0], file=file, view=dropdown_view)
        if isinstance(ctx, disnake.AppCmdInter):
            m = await ctx.original_message()
        dropdown_view.message = m

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

    @progress.command(
        name="update",
        description="Update the template URL.",
        usage="<current name> <new url>",
    )
    async def p_update_url(self, ctx, current_name, new_url):
        async with ctx.typing():
            await self.update(ctx, current_name, new_url=new_url)

    @progress.command(
        name="rename",
        description="Update the template name.",
        usage="<current name> <new name>",
    )
    async def p_update_name(self, ctx, current_name, new_name):
        async with ctx.typing():
            await self.update(ctx, current_name, new_name=new_name)

    @progress.command(
        name="transfer",
        description="Transfer the template ownernership.",
        usage="<current name> <new owner>",
    )
    async def p_update_owner(self, ctx, current_name, new_owner):
        try:
            new_user = await UserConverter().convert(ctx, new_owner)
        except commands.UserNotFound as e:
            return await ctx.send(f"❌ {e}")

        async with ctx.typing():
            await self.update(ctx, current_name, new_owner=new_user)

    async def update(
        self, ctx, current_name, new_url=None, new_name=None, new_owner=None
    ):
        try:
            old_temp, new_temp = await tracked_templates.update_template(
                current_name,
                ctx.author,
                new_url,
                new_name,
                new_owner,
            )
        except ValueError as e:
            return await ctx.send(f":x: {e}")
        embed = disnake.Embed(
            title=f"**✅ Template {old_temp.name} Updated**", color=0x66C5CC
        )

        # Show name update
        if new_name is not None:
            embed.add_field(
                name="Name Changed",
                value=f"`{old_temp.name}` → `{new_temp.name}`",
                inline=False,
            )

        # Show owner update
        if new_owner is not None:
            embed.add_field(
                name="Ownership transferred",
                value=f"<@{old_temp.owner_id}> → <@{new_temp.owner_id}>",
                inline=False,
            )

        # Show all the template info updated
        files = []
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

            # Only show the diff in progress/image if the image or coords changed
            if (
                np.any(old_temp.palettized_array != new_temp.palettized_array)
                or old_temp.ox != new_temp.ox
                or old_temp.oy != new_temp.oy
            ):
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
                    progress += (
                        f"• **Correct Pixels**: {format_number(new_prog)} *(unchanged)*\n"
                    )
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
                    progress += (
                        f"• **Pixels to go**: {format_number(new_togo)} *(unchanged)*\n"
                    )
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
                    diff_gif = await make_before_after_gif(old_temp, new_temp)
                    filename = "diff.gif"
                    files.append(disnake.File(fp=diff_gif, filename=filename))
                    embed.set_image(url=f"attachment://{filename}")
                except Exception:
                    progress += (
                        "**[An error occurred while generating the diff GIF image.]**\n"
                    )
            else:
                progress = "\n__**Image Difference**__\n*(Template image unchanged)*"
            embed.add_field(name="URL Changed", value=info + progress)

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
            if (
                temp.owner_id != ctx.author.id
                and ctx.author.id not in tracked_templates.progress_admins
            ):
                raise ValueError("You cannot delete a template that you don't own.")
            if isinstance(temp, Combo):
                raise ValueError("You cannot delete the combo.")
        except Exception as e:
            return await ctx.send(f":x: {e}")

        confirm_title = (
            f"⚠️ Are you sure you want to DELETE `{temp.name}` from the tracker?"
        )
        confirm_text = "This is **IRREVERSIBLE**!\nThis template and all its stats will be **FOREVER LOST** if you proceed."
        confirm_embed = disnake.Embed(
            title=confirm_title, description=confirm_text, color=0xFFCC00
        )
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
                color=0x3BA55D,
            )

        return await confirm_view.message.edit(embed=embed)

    @_progress.sub_command(name="speed")
    async def _speed(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
        last: str = None,
        groupby: str = commands.Param(default=None, choices=["5min", "hour", "day"]),
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
        parser.add_argument("-last", "-l", nargs="+", default=None)
        parser.add_argument(
            "-groupby", "-g", choices=["5min", "hour", "day"], required=False
        )

        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        async with ctx.typing():
            await self.speed(
                ctx, parsed_args.template, parsed_args.last, parsed_args.groupby
            )

    @staticmethod
    async def speed(ctx, template_name, last: str = None, groupby: str = None):
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
        font = discord_user["font"]
        user_timezone_name = discord_user["timezone"]
        user_timezone = get_timezone(user_timezone_name)

        # get the data
        template_stats = await db_templates.get_all_template_data(template, dt1, dt2)
        if not template_stats:
            return await ctx.send(
                ":x: Couldn't find any data for this template *(try again in ~5 minutes)*."
            )
        template_stats = list([list(r) for r in template_stats])
        df = pd.DataFrame(template_stats, columns=["datetime", "progress"])
        df = df.set_index("datetime")

        dates = [d.to_pydatetime() for d in df.index.tolist()]
        values = df["progress"].tolist()

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
                values = df["progress"].tolist()
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
                if dt1 != datetime.min:
                    values = values[1:]
                    dates = dates[1:]
                if len(dates) > 0:
                    oldest_time = (
                        dates[0]
                        .replace(tzinfo=user_timezone)
                        .astimezone(timezone.utc)
                        .replace(tzinfo=None)
                    )

            if len(dates) == 0 or len(values) == 0:
                return await ctx.send(":x: The time frame given is too short.")
            values = [int(v) for v in values]

        delta_time = latest_time - oldest_time

        if groupby:
            # calculate the speed as px/<groupby>
            values_without_last = values[:-1] if len(values) > 1 else values
            delta_progress = sum(values_without_last)
            average_speed = sum(values_without_last) / len(values_without_last)
            min_value = min(values_without_last)
            max_value = max(values_without_last)
        else:
            # calculate the speed (between the given dates)
            delta_progress = latest_progress - oldest_progress

            if delta_time == timedelta(0):
                return await ctx.send(":x: The time frame given is too short.")
            else:
                speed_px_h = delta_progress / (delta_time / timedelta(hours=1))
                speed_px_d = delta_progress / (delta_time / timedelta(days=1))

        # make the graph
        template_size = template.total_placeable
        if not groupby:
            graph_fig = await get_stats_graph(
                [[template.name, dates, values]],
                "Template Speed",
                theme,
                user_timezone_name,
            )
            # add a line with the size if the max point of the graph is above 80% of the size
            if max([v for v in values if v is not None]) > 0.8 * template_size:
                graph_fig.add_hline(
                    y=template_size,
                    line_dash="dash",
                    annotation_text=f"  Size ({format_number(template_size)})",
                    annotation_position="top left",
                    annotation_font_color=theme.off_color,
                    line=dict(color=theme.off_color, width=3),
                )
        else:
            nb_bars = len(values)
            if nb_bars > 10000:
                return await ctx.send(
                    f":x: That's too many bars too show (**{nb_bars}**). <:bruhkitty:943594789532737586>"
                )
            pos_color = theme.get_palette(1)[0]
            neg_color = theme.red_color
            zero_color = theme.font_color
            bar_colors = []
            for v in values:
                if v is None or v == 0:
                    bar_colors.append(zero_color)
                elif v > 0:
                    bar_colors.append(pos_color)
                elif v < 0:
                    bar_colors.append(neg_color)

            # bar_colors = [get_speed_color(v) for v in values]
            graph_fig = await get_grouped_graph(
                [[template.name, dates, values]],
                f"Template speed (grouped by {groupby})",
                theme,
                user_timezone_name,
                bar_colors,
            )
        graph_image = await fig2img(graph_fig)

        # make the table
        if groupby:
            table_data = [
                [
                    template.name,
                    template_size,
                    delta_progress,
                    average_speed,
                    min_value,
                    max_value,
                ]
            ]
            titles = ["Name", "Size", "Progress", f"px/{groupby}", "min", "max"]
            alignments = ["center", "right", "right", "right", "right", "right"]
        else:
            table_data = [
                [
                    template.name,
                    template_size,
                    delta_progress,
                    speed_px_h,
                    speed_px_d,
                ]
            ]
            titles = ["Name", "Size", "Progress", "px/h", "px/d"]
            alignments = ["center", "right", "right", "right", "right"]
        table_data = [[format_number(c) for c in row] for row in table_data]
        colors = theme.get_palette(1)
        table_image = await table_to_image(
            table_data,
            titles,
            alignments=alignments,
            colors=colors,
            theme=theme,
            font=font,
        )

        # make the embed
        embed = disnake.Embed(
            title=f"**Template Speed for '{template.name}'**", color=0x66C5CC
        )
        embed.url = template.generate_url() if template.url else None
        embed.description = "• Between {} and {}\n".format(
            format_datetime(oldest_time),
            format_datetime(latest_time),
        )
        embed.description += "• Time: `{}`".format(
            td_format(delta_time, hide_seconds=True)
        )

        # merge the table image and graph image
        res_image = await v_concatenate(table_image, graph_image, gap_height=20)
        res_file = await image_to_file(res_image, "template_speed.png", embed)

        await ctx.send(embed=embed, file=res_file)

    @progress.command(
        hidden=True,
        description="Update the list of progress admins (owner only)",
        aliases=["rladmins", "updateadmins"],
    )
    @commands.is_owner()
    async def reload_admins(self, ctx: commands.Context):
        app_info = await self.bot.application_info()
        bot_owner_id = app_info.owner.id
        admins = tracked_templates.load_progress_admins(bot_owner_id)
        msg = "✅ **Progress admin list updated**\nCurrent progress admins:\n"
        for admin_id in admins:
            msg += f"- <@{admin_id}>\n"
        await ctx.send(embed=disnake.Embed(description=msg, color=0x66C5CC))

    @_progress.sub_command(name="timelapse")
    async def _timelapse(
        self,
        inter: disnake.AppCmdInter,
        template: str = commands.Param(autocomplete=autocomplete_templates),
        # display=commands.Param(default="canvas", choices=["canvas", "progress"]),
        last: str = None,
        before=None,
        after=None,
        frames: int = commands.Param(default=40, lt=50, gt=2),
        duration: int = commands.Param(name="frame-duration", default=100, lt=1000, gt=0),
    ):
        """Make a timelapse of the template in a given time frame.

        Parameters
        ----------
        template: The name or URL of a template.
        last: Makes the timelapse in the last x week/day/hour/minute. (format: ?w?d?h?m)
        before: To get the timelapse before a specific date. (format: YYYY-mm-dd HH:MM)
        after: To show the timelapse after a specific date. (format: YYYY-mm-dd HH:MM)
        frames: The number of frames in the timelapse. (default: 40)
        duration: The duration of each frame in milliseconds. (default: 100)
        """
        await inter.response.defer()
        await self.timelapse(inter, template, last, before, after, frames, duration)

    @progress.command(
        name="timelapse",
        description="Make a timelapse of the template in the given time frame.",
        usage="<template> [-last ?w?d?h?m] [-before YYYY-mm-dd HH:MM] [-after YYYY-mm-dd HH:MM] [-frames <frames>] [-duration <duration>]",
        aliases=["tl"],
        help="""
        `<template>`: the name or URL of a template
        `[-last ?w?d?h?m]`: makes the timelapse in the last x week/day/hour/minute (format: ?w?d?h?m)
        `[-before ...]`: to get the timelapse before a specific date (format: YYYY-mm-dd HH:MM)
        `[-after ...]`: to show the timelapse after a specific date (format: YYYY-mm-dd HH:MM)
        `[-frames <frames>]`: the number of frames in the timelapse (default: 40)
        `[-duration <duration>]`: The duration of each frame in milliseconds. (default: 100)
        """,
    )
    async def p_timelapse(self, ctx, *args):
        # parse the arguemnts
        parser = MyParser(add_help=False)
        parser.add_argument("template", action="store")
        # parser.add_argument(
        #     "-display",
        #     action="store",
        #     default="canvas",
        #     choices=["canvas", "progress"],
        # )
        parser.add_argument("-last", "-l", nargs="+", default=None)
        parser.add_argument("-after", nargs="+", default=None)
        parser.add_argument("-before", nargs="+", default=None)
        parser.add_argument("-frames", "-nbframes", type=int, default=40)
        parser.add_argument("-duration", type=int, default=100)

        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        async with ctx.typing():
            await self.timelapse(
                ctx,
                parsed_args.template,
                parsed_args.last,
                parsed_args.before,
                parsed_args.after,
                parsed_args.frames,
                parsed_args.duration,
            )

    async def timelapse(
        self,
        ctx,
        template_name,
        last=None,
        before=None,
        after=None,
        nb_frames=40,
        frame_duration=100,
        display="canvas",
    ):

        # check cooldown
        bucket = self.timelapse_cd.get_bucket(ctx)
        retry_after = bucket.get_retry_after()
        if retry_after:
            raise commands.CommandOnCooldown(bucket, retry_after, self.timelapse_cd.type)

        # get the template
        if parse_template(template_name) is not None:
            template = await get_template_from_url(template_name)
            # check if we have a tracked template with the same image and coords
            template_same_image = tracked_templates.check_duplicate_template(template)
            is_tracked = False
            if template_same_image:
                template = template_same_image
                is_tracked = True
        else:
            template = tracked_templates.get_template(template_name)
            if template is None:
                return await ctx.send(f"No template named `{template_name}` found.")
            is_tracked = True

        min_frames = 2
        max_frames = 50
        if nb_frames > max_frames or nb_frames < min_frames:
            return await ctx.send(
                f":x: The number of frame must be between `{min_frames}` and `{max_frames}`."
            )

        min_duration = 1
        max_duration = 1000
        if frame_duration > max_duration or frame_duration < min_duration:
            return await ctx.send(
                f":x: The frame duration must be between `{min_duration}` and `{max_duration}`."
            )
        last_duration = 1000  # duration for the last frame (in ms)

        # get the user's timezone
        discord_user = await db_users.get_discord_user(ctx.author.id)
        user_timezone = get_timezone(discord_user["timezone"])

        # check on date arguments
        if before is None and after is None and last is None:
            # default to tracking time if no input time is given
            if is_tracked:
                lower_dt, lower_progress = await template.get_progress_at(datetime.min)
                higher_dt, higher_progress = await template.get_progress_at(
                    datetime.utcnow()
                )
                if lower_dt is None or higher_dt is None:
                    return await ctx.send(
                        ":x: Not enough data to find the start-tracking date, input dates manually with the 'before/after/last' options."
                    )
            else:
                lower_dt = datetime.min
                higher_dt = datetime.max
            lower_dt = lower_dt.replace(tzinfo=timezone.utc)
            higher_dt = higher_dt.replace(tzinfo=timezone.utc)
        else:
            try:
                lower_dt, higher_dt = get_datetimes_from_input(
                    user_timezone, last, before, after, 15
                )
            except ValueError as e:
                return await ctx.send(f":x: {e}")
            canvas_start_date = await db_stats.get_canvas_start_date(
                await stats.get_canvas_code()
            )
            canvas_start_date = canvas_start_date.replace(tzinfo=timezone.utc)
            lower_dt = max(canvas_start_date, lower_dt)

        # get the snapshots URLs
        canvas_code = await stats.get_canvas_code()
        snapshot_urls = await db_stats.get_snapshots_between(
            lower_dt.astimezone(timezone.utc),
            higher_dt.astimezone(timezone.utc),
            canvas_code,
        )
        if len(snapshot_urls) < 2:
            return await ctx.send(":x: The Time Frame Given is too short.")
        snapshot_urls = shorten_list(snapshot_urls, min(nb_frames, len(snapshot_urls)))
        nb_frames = len(snapshot_urls)

        # enable the cooldown
        self.timelapse_cd.update_rate_limit(ctx)

        # download the snapshots
        embed = disnake.Embed(color=0x66C5CC, title="Timelapse")
        embed.description = "<a:typing:675416675591651329> **Downloading snapshots**...\n"
        m = await ctx.send(embed=embed)
        if m is None:
            m = await ctx.original_message()

        MAX_TASKS = 5  # number of simultaneous downloads
        MAX_TIME = 120  # timeout before error
        start = time.time()

        async def download_frame(url, sess, sem):
            async with sem:
                async with sess.get(url) as res:
                    content = await res.read()
                if res.status != 200:
                    return None
                else:
                    return Image.open(BytesIO(content))

        tasks = []
        sem = asyncio.Semaphore(MAX_TASKS)
        try:
            async with aiohttp.client.ClientSession() as sess:
                for url in snapshot_urls:
                    tasks.append(
                        asyncio.wait_for(
                            download_frame(url[2], sess, sem),
                            timeout=MAX_TIME,
                        )
                    )
                snapshot_images = await asyncio.gather(*tasks)
        except Exception:
            embed.description = "**:x: Downloading snapshots**... error\n"
            embed.description += "An error occurred while downloading the snapshots."
            embed.color = disnake.Color.red()
            await m.edit(embed=embed)
            return

        # crop the template area
        embed.description = "✅ **Downloading the snapshots**... done!\n\n<a:typing:675416675591651329> **Cropping the snapshots**..."
        await m.edit(embed=embed)
        frames = []
        for snapshot_image in snapshot_images:
            if display == "canvas":
                offset = 5  # offset around the template area
                ss_frame = snapshot_image.crop(
                    (
                        template.ox - offset,
                        template.oy - offset,
                        template.ox + template.width + offset,
                        template.oy + template.height + offset,
                    )
                )
                snapshot_image.close()
            elif display == "progress":
                snapshot_array = reduce(snapshot_image, get_rgba_palette())
                template.update_progress(snapshot_array)
                ss_frame = template.get_progress_image(board_array=snapshot_array)

            # upscale the images if they're too big
            scale = find_upscale(ss_frame)
            if scale > 1:
                ss_frame_resized = ss_frame.resize(
                    (ss_frame.width * scale, ss_frame.height * scale), Image.NEAREST
                )
                ss_frame.close()
            else:
                ss_frame_resized = ss_frame
            frames.append(ss_frame_resized)

        embed.description = "✅ **Downloading the snapshots**... done!\n\n✅ **Cropping the snapshots**... done!"
        embed.description += (
            "\n\n<a:typing:675416675591651329> **Saving and sending the GIF**..."
        )
        await m.edit(embed=embed)
        # combine the frames to make a GIF
        animated_img = BytesIO()
        frames[0].save(
            animated_img,
            format="GIF",
            append_images=frames[1:],
            save_all=True,
            duration=[frame_duration] * (len(frames) - 1) + [last_duration],
            loop=0,
        )
        animated_img.seek(0)

        # prepare the embed with the informations
        t0 = snapshot_urls[0][0]
        t1 = snapshot_urls[-1][0]
        diff_time = t1 - t0
        time_per_frame = diff_time / nb_frames
        description = "• Between {} and {}\n• Total time: `{}`\n• 1 frame = `{}`\n• Number of frames: `{}`\n• Frame duration: `{}ms` `({}fps)`".format(
            format_datetime(t0),
            format_datetime(t1),
            td_format(diff_time, short_format=True, hide_seconds=True),
            td_format(time_per_frame, short_format=True, hide_seconds=True),
            nb_frames,
            frame_duration,
            format_number(1 / (frame_duration / 1000)),
        )
        embed.description = description
        embed.set_footer(text=f"Done in {format_number(time.time()-start)}s")
        file = disnake.File(fp=animated_img, filename="timelapse.gif")
        embed.set_image(url="attachment://timelapse.gif")

        # send the final GIF
        try:
            await m.edit(embed=embed, file=file)
        except Exception:
            embed.set_footer(text="")
            embed.description = "✅ **Downloading the snapshots**... done!\n\n✅ **Cropping the snapshots**... done!"
            embed.description += "\n\n:x: **Saving and sending the GIF**... error\n(most likely the GIF is too big for discord's limit of 8MB)"
            embed.description += (
                "\n\n<a:typing:675416675591651329> **Uploading to imgur**..."
            )
            await m.edit(embed=embed)
            try:
                animated_img.seek(0)
                imgur_link = await imgur_app.upload_image(animated_img.read(), True)
            except Exception as e:
                if isinstance(e, BadResponseError) and "400" in str(e):
                    cmd = (
                        "frames:<nb frames>"
                        if isinstance(ctx, disnake.AppCmdInter)
                        else "-frames <nb frames>"
                    )
                    msg = "error\nMaybe the image was too big for imgur too??\n"
                    msg += f"Try making the timelapse with less than {nb_frames} frames\n"
                    msg += f"(add `{cmd}` to the command)."
                else:
                    msg = "unexpected error"
                embed.description = "✅ **Downloading the snapshots**... done!\n\n✅ **Cropping the snapshots**... done!"
                embed.description += "\n\n:x: **Saving and sending the GIF**... error\n(most likely the GIF is too big for discord's limit of 8MB)"
                embed.description += f"\n\n:x: **Uploading to imgur**... {msg}"
                embed.color = disnake.Color.red()
                await m.edit(embed=embed)
            else:
                embed.description = description
                embed.set_footer(text=f"Done in {format_number(time.time()-start)}s")
                embed.set_image(url=imgur_link)
                await m.edit(embed=embed)
        for frame in frames:
            frame.close()

    @_progress.sub_command(name="coords")
    async def _coords(
        self,
        inter: disnake.AppCmdInter,
        coords: str,
    ):
        """Show all the tracked templates at the given coordinates.

        Parameters
        ----------
        coords: Coordinates in the format: x y or pxls link."""
        await inter.response.defer()
        await self.list(inter, coords=coords)

    @progress.command(
        name="coords",
        description="Show all the tracked templates at the given coordinates.",
        usage="<x> <y>",
        help="""`<x> <y>`: Coordinates in the format: x y or pxls link""",
        aliases=["coord", "coordinates", "coordinate"],
    )
    async def p_coords(self, ctx, *, coords):

        async with ctx.typing():
            await self.list(ctx, coords=coords)


pos_speed_palette = get_gradient_palette(["#ffffff", "#70dd13", "#31a117"], 101)
neg_speed_palette = get_gradient_palette(["#ff6474", "#ff0000", "#991107"], 101)
percentage_palette = get_gradient_palette(
    ["#e21000", "#fca80e", "#fff491", "#beff40", "#31a117"], 101
)


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


def setup(bot: commands.Bot):
    bot.add_cog(Progress(bot))
