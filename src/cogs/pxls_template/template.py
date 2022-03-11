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
    format_number,
    get_image_from_message,
    image_to_file,
)
from utils.image.image_utils import remove_white_space
from utils.pxls.template import (
    STYLES,
    get_style,
    parse_style_image,
    templatize,
    reduce,
    get_rgba_palette,
)
from utils.setup import stats
from utils.utils import get_content


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
        """
        await inter.response.defer()
        await self.template(inter, image, style, glow, title, ox, oy, nocrop, matching)

    @_template.autocomplete("style")
    async def autocomplete_style(self, inter: disnake.AppCmdInter, user_input: str):
        styles = [s["name"] for s in STYLES]
        return [s for s in styles if user_input.lower() in s.lower()][:25]

    @commands.command(
        name="template",
        description="Generate a template link from an image.",
        usage="<image|url> [-style <style>] [-glow] [-title <title>] [-ox <ox>] [-oy <oy>] [-nocrop] [-matching fast|accurate]",
        help="""- `<image|url>`: an image URL or an attached file
              - `[-style <style>]`: the name or URL of a template style (use `>styles` to see the list)
              - `[-glow]`: add glow to the template
              - `[-title <title>]`: the template title
              - `[-ox <ox>]`: template x-position
              - `[-oy <oy>]`: template y-position
              - `[-nocrop]`: if you don't want the template to be automatically cropped
              - `[-matching fast|accurate]`: the color matching algorithm to use""",
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

        try:
            parsed_args = parser.parse_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        url = parsed_args.url[0] if parsed_args.url else None
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
            )

    async def template(
        self, ctx, image_url, style_name, glow, title, ox, oy, nocrop, matching
    ):
        # get the image from the message
        try:
            img, url = await get_image_from_message(ctx, image_url)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")

        start = time.time()
        # check on the style
        if style_name and re.match(IMAGE_URL_REGEX, style_name):
            # if the style is an image URL, we try to use the image as style
            style_url = style_name
            try:
                style_image_bytes = await get_content(style_url, "image")
            except Exception as e:
                return await ctx.send(f"❌ {e}")
            style_image = Image.open(BytesIO(style_image_bytes))
            style_image = style_image.convert("RGBA")
            style_array, style_size = parse_style_image(style_image)
            if style_array is None:
                return await ctx.send(
                    ":x: There was an error while parsing the style image, make sure it is valid."
                )
            style = {
                "name": f"[[From User]]({style_url})",
                "size": style_size,
                "array": style_array,
            }
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
                return await ctx.send(
                    f"❌ Unknown style '{style_name}'.\n{styles_available}"
                )

        # check on the size
        output_size = img.width * img.height * style["size"]
        limit = int(7e6)
        if output_size > limit:
            msg = f"You're trying to generate a **{format_number(output_size)}** pixels image.\n"
            msg += f"This exceeds the bot's limit of **{format_number(limit)}** pixels.\n"
            msg += "\n*Try using a style with a smaller size or a smaller image.*"
            return await ctx.send(
                embed=disnake.Embed(
                    title=":x: Size limit exceeded",
                    description=msg,
                    color=disnake.Color.red(),
                )
            )
        # check on the glow
        if glow:
            glow_opacity = 0.2
        else:
            glow_opacity = 0

        # check on the matching
        if matching is None:
            matching = "fast"  # default = 'fast'

        # crop the white space around the image
        if not (nocrop):
            img = remove_white_space(img)

        # reduce the image to the pxls palette
        img_array = np.array(img)
        palette = get_rgba_palette()
        reduced_array = await self.bot.loop.run_in_executor(
            None, reduce, img_array, palette, matching
        )

        # convert the image to a template style
        template_array = await self.bot.loop.run_in_executor(
            None, templatize, style, reduced_array, glow_opacity
        )
        template_image = Image.fromarray(template_array)
        total_amount = np.sum(reduced_array != 255)
        total_amount = format_number(int(total_amount))
        end = time.time()

        # create and send the image
        embed = disnake.Embed(title="**Template Image**", color=0x66C5CC)
        embed.description = f"**Title**: {title if title else '`N/A`'}\n**Style**: {style['name']}\n**Glow**: {'yes' if glow else 'no'}\n**Size**: {total_amount} pixels ({img.width}x{img.height})"
        embed.set_footer(
            text="Warning: if you delete this message the template might break."
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        reduced_image = Image.fromarray(stats.palettize_array(reduced_array))
        reduced_file = image_to_file(reduced_image, "reduced.png")
        embed.set_thumbnail(url="attachment://reduced.png")
        file = image_to_file(template_image, "template.png", embed)
        m = await ctx.send(embed=embed, files=[file, reduced_file])
        if isinstance(ctx, disnake.AppCmdInter):
            m = await ctx.original_message()

        # create a template link with the sent image
        template_title = f"&title={urllib.parse.quote(title)}" if title else ""
        template_image_url = m.embeds[0].image.url
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
        template_url = f"https://pxls.space/#x={x}&y={y}&scale=5&template={urllib.parse.quote(template_image_url)}&ox={t_ox}&oy={t_oy}&tw={img.width}&oo=1{template_title}"
        template_embed = disnake.Embed(
            title="**Template Link**", description=template_url, color=0x66C5CC
        )
        template_embed.set_footer(text=f"Generated in {round((end-start),3)}s")
        await ctx.send(embed=template_embed)

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
