from datetime import datetime, timedelta
import os
import asyncio
import re
import disnake
import numpy as np
import urllib.parse
import time
from PIL import Image
from io import BytesIO
from disnake.ext import commands
from utils.arguments_parser import MyParser
from utils.discord_utils import (
    IMAGE_URL_REGEX,
    AuthorView,
    autocomplete_builtin_palettes,
    format_number,
    get_image_from_message,
    image_to_file,
)
from utils.image.image_utils import get_colors_from_input, remove_white_space
from utils.pxls.template import (
    STYLES,
    get_style,
    parse_style_image,
    templatize,
    reduce,
    get_rgba_palette,
)
from utils.setup import stats, db_users, db_stats
from utils.time_converter import td_format
from utils.utils import get_content


class TemplateView(AuthorView):
    def __init__(self, author: disnake.User, template_url, message, embed, has_title):
        super().__init__(author, timeout=300)
        self.template_url = template_url
        self.message = message
        self.embed: disnake.Embed = embed
        self.children.insert(
            0, disnake.ui.Button(label="Open Template", url=self.template_url)
        )
        if has_title:
            self.remove_item(self.children[1])

    async def on_timeout(self) -> None:
        # disable all the buttons except the url one
        for c in self.children[1:]:
            self.remove_item(c)
        await self.message.edit(view=self)

    @disnake.ui.button(
        label="Add a Title",
        style=disnake.ButtonStyle.green,
    )
    async def add_title(
        self, button: disnake.ui.Button, button_inter: disnake.MessageInteraction
    ):
        # send a modal
        modal_id = os.urandom(16).hex()
        await button_inter.response.send_modal(
            title="Add a title to the template",
            custom_id=modal_id,
            components=[
                disnake.ui.TextInput(
                    label="Title",
                    placeholder="Very Cool Template v42 (final-final for real) [WIP] (solo)",
                    custom_id="title",
                    min_length=1,
                    max_length=256,
                    style=disnake.TextInputStyle.short,
                ),
            ],
        )

        try:
            # wait until the user submits the modal.
            modal_inter: disnake.ModalInteraction = await button_inter.bot.wait_for(
                "modal_submit",
                check=lambda i: i.custom_id == modal_id
                and i.author.id == button_inter.author.id,
                timeout=300,
            )
        except asyncio.TimeoutError:
            # The user didn't submit the modal in the specified period of time.
            # This is done since Discord doesn't dispatch any event for when a modal is closed/dismissed.
            return

        title = modal_inter.text_values["title"].strip()
        template_title = f"&title={urllib.parse.quote(title, safe='')}"
        self.template_url += template_title
        # update the view
        self.children[0].url = self.template_url
        self.remove_item(self.children[1])
        # update the embed
        self.embed.set_field_at(
            -1, name="Template Link", value=self.template_url, inline=False
        )
        self.embed._fields[0]["value"] = self.embed._fields[0]["value"].replace(
            "N/A", title
        )
        await button_inter.message.edit(view=self, embed=self.embed)
        # confirmation message (because we HAVE to respond something to the modal inter)
        await modal_inter.response.send_message(
            embed=disnake.Embed(
                color=0x66C5CC, title="✅ Template title successfully added."
            ),
            ephemeral=True,
        )


class Template(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="template")
    async def _template(
        self,
        inter: disnake.AppCmdInter,
        image: str = None,
        style: str = None,
        glow: bool = False,
        title: str = None,
        ox: int = None,
        oy: int = None,
        nocrop: bool = False,
        matching: str = commands.Param(
            default=None,
            choices={"Fast (default)": "fast", "Accurate (slower)": "accurate"},
        ),
        palette: str = commands.Param(
            default=None,
            autocomplete=autocomplete_builtin_palettes,
        ),
    ):
        """Generate a template link from an image.

        Parameters
        ----------
        image: The URL of the image you want to templatize.
        style: The name or URL of a template style. (default: custom)
        glow: To add glow to the template. (default: False)
        title: The template title.
        ox: The template x-position.
        oy: The template y-position.
        nocrop: If you don't want the template to be automatically cropped. (default: False)
        matching: The color matching algorithm to use.
        palette: A palette name or list of colors (name or hex) seprated by a comma. (default: pxls)
        """
        await inter.response.defer()
        await self.template(
            inter, image, style, glow, title, ox, oy, nocrop, matching, palette
        )

    @_template.autocomplete("style")
    async def autocomplete_style(self, inter: disnake.AppCmdInter, user_input: str):
        styles = [s["name"] for s in STYLES]
        return [s for s in styles if user_input.lower() in s.lower()][:25]

    @commands.command(
        name="template",
        description="Generate a template link from an image.",
        usage="<image|url> [-style <style>] [-glow] [-title <title>] [-ox <ox>] [-oy <oy>] [-nocrop] [-matching fast|accurate] [-palette ...]",
        help="""- `<image|url>`: an image URL or an attached file
              - `[-style <style>]`: the name or URL of a template style (use `>styles` to see the list)
              - `[-glow]`: add glow to the template
              - `[-title <title>]`: the template title
              - `[-ox <ox>]`: template x-position
              - `[-oy <oy>]`: template y-position
              - `[-nocrop]`: if you don't want the template to be automatically cropped
              - `[-matching fast|accurate]`: the color matching algorithm to use
              - `[-palette ...]`: the palette to use for the template (palette name or list of colors seprated by a comma.)""",
        aliases=["templatize", "temp"],
    )
    async def p_template(self, ctx, *args):

        parser = MyParser(add_help=False)
        parser.add_argument("url", action="store", nargs="*")
        parser.add_argument("-style", action="store", required=False)
        parser.add_argument("-glow", action="store_true", default=False)
        parser.add_argument("-title", action="store", required=False)
        parser.add_argument("-ox", action="store", required=False)
        parser.add_argument("-oy", action="store", required=False)
        parser.add_argument("-nocrop", action="store_true", default=False)
        parser.add_argument("-matching", choices=["fast", "accurate"], required=False)
        parser.add_argument("-palette", action="store", nargs="*")

        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        url = parsed_args.url[0] if parsed_args.url else None
        palette = " ".join(parsed_args.palette) if parsed_args.palette else None
        async with ctx.typing():
            await self.template(
                ctx,
                url,
                parsed_args.style,
                parsed_args.glow,
                parsed_args.title,
                parsed_args.ox,
                parsed_args.oy,
                parsed_args.nocrop,
                parsed_args.matching,
                palette,
            )

    @staticmethod
    async def template(
        ctx, image_url, style_name, glow, title, ox, oy, nocrop, matching, palette=None
    ):
        # get the image from the message
        try:
            img, url = await get_image_from_message(ctx, image_url)
        except ValueError as e:
            await ctx.send(f"❌ {e}")
            return False

        start = time.time()
        # check on the style
        if style_name and re.match(IMAGE_URL_REGEX, style_name):
            # if the style is an image URL, we try to use the image as style
            style_url = style_name
            try:
                style_image_bytes = await get_content(style_url, "image")
            except Exception as e:
                await ctx.send(f"❌ {e}")
                return False
            style_image = Image.open(BytesIO(style_image_bytes))
            style_image = style_image.convert("RGBA")
            style_array, style_size = parse_style_image(style_image)
            if style_array is None:
                await ctx.send(
                    ":x: There was an error while parsing the style image, make sure it is valid."
                )
                return False
            style = {
                "name": f"[[From User]]({style_url})",
                "size": style_size,
                "array": style_array,
            }
            style_name = f"[[From User]]({style_url}){' `(+ glow)`' if glow else ''}"
        else:
            # the style is a style name, we search it from the built-in styles
            if not style_name:
                style_name = "custom"  # default style
            style = get_style(style_name)
            if not style:
                styles_available = "**Available Styles:**\n"
                for s in STYLES:
                    styles_available += ("\t• {0} ({1}x{1})\n").format(
                        s["name"], s["size"]
                    )
                await ctx.send(f"❌ Unknown style `{style_name}`.\n{styles_available}")
                return False
            style_name = f"`{style['name']}{' (+ glow)' if glow else ''}`"

        # check on the size
        output_size = img.width * img.height * style["size"] ** 2
        limit = int(100e6)
        if output_size > limit:
            msg = f"You're trying to generate a **{format_number(output_size)}** pixels image.\n"
            msg += f"This exceeds the bot's limit of **{format_number(limit)}** pixels.\n"
            msg += "\n*Try using a style with a smaller size or a smaller image.*"
            await ctx.send(
                embed=disnake.Embed(
                    title=":x: Size limit exceeded",
                    description=msg,
                    color=disnake.Color.red(),
                )
            )
            return False
        # check on the glow
        if glow:
            glow_opacity = 0.2
        else:
            glow_opacity = 0

        # check on the matching
        if matching is None:
            matching = "fast"  # default = 'fast'

        # get the palette
        if not palette:
            palette_names = ["pxls (current)"]
            rgba_palette = get_rgba_palette()
            hex_palette = None  # default pxls
        else:
            try:
                rgba_palette, hex_palette, palette_names = get_colors_from_input(
                    palette, accept_colors=True, accept_palettes=True
                )
            except ValueError as e:
                return await ctx.send(f":x: {e}")

        # crop the white space around the image
        if not (nocrop):
            img = remove_white_space(img)

        # reduce the image to the given palette
        img_array = np.array(img)
        loop = asyncio.get_running_loop()
        reduced_array = await loop.run_in_executor(
            None, reduce, img_array, rgba_palette, matching
        )

        # convert the image to a template style
        loop = asyncio.get_running_loop()
        template_array = await loop.run_in_executor(
            None, templatize, style, reduced_array, glow_opacity, rgba_palette
        )
        template_image = Image.fromarray(template_array)
        total_amount = int(np.sum(reduced_array != 255))
        end = time.time()

        # Calculate an ETA
        estimate = None
        discord_user = await db_users.get_discord_user(ctx.author.id)
        pxls_user_id = discord_user["pxls_user_id"]
        if pxls_user_id:
            try:
                pxls_name = await db_users.get_pxls_user_name(pxls_user_id)
                canvas_stats = stats.get_canvas_stat(pxls_name) or 0
                canvas_code = await stats.get_canvas_code()
                canvas_start = await db_stats.get_canvas_start_date(canvas_code)
                if canvas_start:
                    canvas_duration = datetime.utcnow() - canvas_start
                    canvas_duration = canvas_duration / timedelta(days=1)
                    if canvas_duration > 0:
                        canvas_speed = canvas_stats / canvas_duration
                        if canvas_speed != 0:
                            eta = timedelta(days=(total_amount / canvas_speed))
                            eta = td_format(eta, short_format=True, max_unit="day")
                        else:
                            eta = "Infinity days"
                        estimate = f"`{eta}` (at `{format_number(canvas_speed)}` px/day)"
            except Exception:
                pass

        # create and send the image
        embed = disnake.Embed(title="**Template**", color=0x66C5CC)
        template_info = f"Title: `{title if title else 'N/A'}`\n"
        template_info += f"Style: {style_name}\n"

        if palette:
            template_info += f"Palette: {', '.join(palette_names)}\n"
        embed.add_field(name="**Template Info**", value=template_info)
        template_size = f"Size: `{format_number(total_amount)}` pixels\n"
        template_size += f"Dimensions: `{img.width} x {img.height}`\n"

        embed.add_field(name="**Template Size**", value=template_size)
        if estimate:
            embed.add_field(name="Estimate", value=estimate, inline=False)
        embed.set_footer(
            text=f"⏲️ Generated in {round((end-start),3)}s\n⚠️ Warning: if you delete this message the template WILL break."
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        embed.set_thumbnail(url="attachment://template.png")
        file = await image_to_file(template_image, "template.png")

        m = await ctx.send(embed=embed, file=file)
        if isinstance(ctx, (disnake.AppCmdInter, disnake.MessageInteraction)):
            m = await ctx.original_message()

        # create a template link with the sent image
        template_title = f"&title={urllib.parse.quote(title, safe='')}" if title else ""
        template_image_url = m.embeds[0].thumbnail.url
        if ox or oy:
            t_ox = int(ox) if (ox and str(ox).isdigit()) else 0
            t_oy = int(oy) if (oy and str(oy).isdigit()) else 0
            x = int(t_ox + img.width / 2)
            y = int(t_oy + img.height / 2)
        else:
            try:  # we're using a try/except block so we can still make templates if the board info is unreachable
                x = int(stats.board_info["width"] / 2)
                y = int(stats.board_info["height"] / 2)
            except Exception:
                x = y = 500
            t_ox = int(x - img.width / 2)
            t_oy = int(y - img.height / 2)
        template_url = f"https://pxls.space/#x={x}&y={y}&scale=5&template={urllib.parse.quote(template_image_url, safe='')}&ox={t_ox}&oy={t_oy}&tw={img.width}{template_title}"

        # update the embed with the link in a new field
        embed.add_field(name="**Template Link**", value=template_url, inline=False)
        view = TemplateView(ctx.author, template_url, m, embed, bool(title))
        await m.edit(embed=embed, view=view)
        return True

    @commands.command(
        name="styles",
        description="List the template styles available.",
        aliases=["style"],
    )
    async def styles(self, ctx):
        styles_available = "**Available Styles:**\n"
        for s in STYLES:
            styles_available += ("\t• {0} ({1}x{1})\n").format(s["name"], s["size"])
        return await ctx.send(styles_available)


def setup(bot: commands.Bot):
    bot.add_cog(Template(bot))
