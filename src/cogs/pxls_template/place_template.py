import asyncio
import re
import disnake
import numpy as np
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
from utils.image.image_utils import get_builtin_palette
from utils.pxls.template import (
    STYLES,
    get_style,
    parse_style_image,
    templatize,
    reduce,
)
from utils.setup import stats
from utils.utils import get_content


class PlaceTemplate(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.slash_command(name="place-template")
    async def _template(
        self,
        inter: disnake.AppCmdInter,
        image: str = None,
        style: str = None,
        glow: bool = False,
        ox: int = None,
        oy: int = None,
        matching: str = commands.Param(
            default=None,
            choices={"Accurate (default)": "accurate", "Fast": "fast"},
        ),
    ):
        """Generate a template image for r/place overlays.

        Parameters
        ----------
        image: The URL of the image you want to templatize.
        style: The name or URL of a template style. (default: custom)
        glow: To add glow to the template. (default: False)
        ox: The template x-position.
        oy: The template y-position.
        matching: The color matching algorithm to use.
        """
        await inter.response.defer()
        await self.template(inter, image, style, glow, ox, oy, matching)

    @_template.autocomplete("style")
    async def autocomplete_style(self, inter: disnake.AppCmdInter, user_input: str):
        styles = [s["name"] for s in STYLES]
        return [s for s in styles if user_input.lower() in s.lower()][:25]

    @commands.command(
        name="placetemplate",
        description="Generate a template image for r/place overlays.",
        usage="<image|url> [-style <style>] [-glow] [-ox <ox>] [-oy <oy>] [-nocrop] [-matching fast|accurate]",
        help="""- `<image|url>`: an image URL or an attached file
              - `[-style <style>]`: the name or URL of a template style (use `>styles` to see the list)
              - `[-glow]`: add glow to the template
              - `[-ox <ox>]`: template x-position
              - `[-oy <oy>]`: template y-position
              - `[-matching fast|accurate]`: the color matching algorithm to use""",
        aliases=["placetemp"],
    )
    async def p_template(self, ctx, *args):

        parser = MyParser(add_help=False)
        parser.add_argument("url", action="store", nargs="*")
        parser.add_argument("-style", action="store", required=False)
        parser.add_argument("-glow", action="store_true", default=False)
        parser.add_argument("-ox", action="store", required=False)
        parser.add_argument("-oy", action="store", required=False)
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
                parsed_args.ox,
                parsed_args.oy,
                parsed_args.matching,
            )

    @staticmethod
    async def template(ctx, image_url, style_name, glow, ox, oy, matching):
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
        else:
            # the style is a style name, we search it from the built-in styles
            if not style_name:
                style_name = "dotted"  # default style
            style = get_style(style_name)
            if not style:
                styles_available = "**Available Styles:**\n"
                for s in STYLES:
                    styles_available += ("\t• {0} ({1}x{1})\n").format(
                        s["name"], s["size"]
                    )
                await ctx.send(f"❌ Unknown style '{style_name}'.\n{styles_available}")
                return False

        # check on the size
        output_size = img.width * img.height * style["size"] ** 2
        limit = int(121e6)
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
            matching = "accurate"  # default = 'accurate'

        # check on coords
        ox = int(ox) if (ox and str(ox).isdigit()) else 0
        oy = int(oy) if (oy and str(oy).isdigit()) else 0

        # reduce the image to the r/place palette
        img_array = np.array(img)
        palette = get_builtin_palette("place", as_rgba=True)
        loop = asyncio.get_running_loop()
        reduced_array = await loop.run_in_executor(
            None, reduce, img_array, palette, matching
        )

        # paste the image at the given coords
        canvas = np.full((1000, 2000), 255)
        try:
            canvas[oy : oy + img.height, ox : ox + img.width] = reduced_array
        except Exception:
            return await ctx.send(
                ":x: Error: the image has some parts outside the canvas."
            )

        # convert the image to a template style
        loop = asyncio.get_running_loop()
        template_array = await loop.run_in_executor(
            None, templatize, style, canvas, glow_opacity, "place"
        )
        template_image = Image.fromarray(template_array)
        total_amount = np.sum(reduced_array != 255)
        total_amount = format_number(int(total_amount))
        end = time.time()

        # create and send the image
        embed = disnake.Embed(title="**Template Image**", color=0x66C5CC)
        embed.description = f"**Style**: {style['name']}\n**Glow**: {'yes' if glow else 'no'}\n**Size**: {total_amount} pixels ({img.width}x{img.height})"
        embed.set_footer(
            text="⚠️ Warning: if you delete this message the template WILL break."
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.display_avatar)
        reduced_image = Image.fromarray(
            stats.palettize_array(
                reduced_array,
                ["#" + c for c in get_builtin_palette("place", as_rgba=False)],
            )
        )
        reduced_file = await image_to_file(reduced_image, "reduced.png")
        embed.set_thumbnail(url="attachment://reduced.png")
        file = await image_to_file(template_image, "template.png", embed)
        m = await ctx.send(embed=embed, files=[file, reduced_file])
        if isinstance(ctx, (disnake.AppCmdInter, disnake.MessageInteraction)):
            m = await ctx.original_message()

        # create a template link with the sent image
        template_image_url = m.embeds[0].image.url

        text = "**HOW TO USE?**\n"
        text += "1. Install [Tapermonkey (Chrome/Opera)](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo?hl=en) or [Violentmonkey (Firefox)](https://addons.mozilla.org/en-US/firefox/addon/violentmonkey/).\n"
        text += "2. Go to [r/place](https://www.reddit.com/r/place/), click on the extension and create a new script.\n"
        text += "3. Go to this [GitHub Gist](https://gist.github.com/oralekin/240d536d13d0a87ecf2474658115621b) and copy and paste the code.\n"
        text += '4. Replace the line `i.src = "<some image link>";` with the following:\n'
        text += f'```i.src = "{template_image_url}";```\n'
        text += "5. Go back to [r/place](https://www.reddit.com/r/place/) and refresh the page."

        template_embed = disnake.Embed(
            title="**Template Link**", description=text, color=0x66C5CC
        )
        template_embed.set_footer(text=f"Generated in {round((end-start),3)}s")
        await ctx.send(embed=template_embed)
        return True


def setup(bot: commands.Bot):
    bot.add_cog(PlaceTemplate(bot))
