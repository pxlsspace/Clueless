import discord
import numpy as np
import urllib.parse
import time
from PIL import Image
from io import BytesIO
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option, create_choice

from utils.arguments_parser import MyParser
from utils.discord_utils import format_number, get_image_from_message, image_to_file
from utils.image.image_utils import remove_white_space
from utils.pxls.template import STYLES, get_style, templatize, reduce, get_rgba_palette
from utils.setup import stats, GUILD_IDS


class Template(commands.Cog):
    def __init__(self, client) -> None:
        self.client = client

    @cog_ext.cog_slash(
        name="template",
        description="Generate a template link from an image.",
        guild_ids=GUILD_IDS,
        options=[
            create_option(
                name="image",
                description="The URL of the image you want to templatize.",
                option_type=3,
                required=False,
            ),
            create_option(
                name="style",
                description="The template style you want. (default: custom)",
                option_type=3,
                required=False,
                choices=[
                    create_choice(name=s["name"], value=s["name"]) for s in STYLES
                ],
            ),
            create_option(
                name="glow",
                description="To add glow to the template. (default: False)",
                option_type=5,
                required=False,
            ),
            create_option(
                name="title",
                description="The template title.",
                option_type=3,
                required=False,
            ),
            create_option(
                name="ox",
                description="Template x-position.",
                option_type=4,
                required=False,
            ),
            create_option(
                name="oy",
                description="Template y-position.",
                option_type=4,
                required=False,
            ),
            create_option(
                name="nocrop",
                description="If you don't want the template to be automatically cropped. (default: False)",
                option_type=5,
                required=False,
            ),
        ],
    )
    async def _highlight(
        self,
        ctx: SlashContext,
        image=None,
        style=None,
        glow=None,
        title=None,
        ox=None,
        oy=None,
        nocrop=None,
    ):
        await ctx.defer()
        await self.template(ctx, image, style, glow, title, ox, oy, nocrop)

    @commands.command(
        name="template",
        description="Generate a template link from an image.",
        usage="<image|url> [-style <style>] [-glow] [-title <title>] [-ox <ox>] [-oy <oy>]",
        help="""- `<image|url>`: an image URL or an attached file
              - `[-style <style>]`: the template style you want (use `>styles` to see the list)
              - `[-glow]`: add glow to the template
              - `[-title <title>]`: the template title
              - `[-ox <ox>]`: template x-position
              - `[-oy <oy>]`: template y-position
              - `[-nocrop]`: if you don't want the template to be automatically cropped""",
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
            )

    async def template(self, ctx, image_url, style_name, glow, title, ox, oy, nocrop):
        # get the image from the message
        try:
            img, url = await get_image_from_message(ctx, image_url, accept_emojis=False)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        img = Image.open(BytesIO(img))
        img = img.convert("RGBA")

        start = time.time()
        # check on the style
        if not style_name:
            style_name = "custom"  # default style
        style = get_style(style_name)
        if not style:
            styles_available = "**Available Styles:**\n"
            for s in STYLES:
                styles_available += ("\t• {0} ({1}x{1})\n").format(s["name"], s["size"])
            return await ctx.send(
                f"❌ Unknown style '{style_name}'.\n{styles_available}"
            )

        # check on the glow
        if glow:
            glow_opacity = 0.2
        else:
            glow_opacity = 0

        # crop the white space around the image
        if not (nocrop):
            img = remove_white_space(img)

        # reduce the image to the pxls palette
        img_array = np.array(img)
        palette = get_rgba_palette()
        reduced_array = await self.client.loop.run_in_executor(
            None, reduce, img_array, palette
        )

        # convert the image to a template style
        template_array = await self.client.loop.run_in_executor(
            None, templatize, style, reduced_array, glow_opacity
        )
        template_image = Image.fromarray(template_array)
        total_amount = np.sum(reduced_array != 255)
        total_amount = format_number(int(total_amount))
        end = time.time()

        # create and send the image
        embed = discord.Embed(title="**Template Image**", color=0x66C5CC)
        embed.description = f"**Title**: {title if title else '`N/A`'}\n**Style**: {style_name}\n**Glow**: {'yes' if glow else 'no'}\n**Size**: {total_amount} pixels ({img.width}x{img.height})"
        embed.set_footer(
            text="Warning: if you delete this message the template might break."
        )
        embed.set_author(name=ctx.author, icon_url=ctx.author.avatar_url)
        reduced_image = Image.fromarray(stats.palettize_array(reduced_array))
        reduced_file = image_to_file(reduced_image, "reduced.png")
        embed.set_thumbnail(url="attachment://reduced.png")
        file = image_to_file(template_image, "template.png")
        m = await ctx.send(embed=embed, files=[file, reduced_file])

        # create a template link with the sent image
        template_title = f"&title={urllib.parse.quote(title)}" if title else ""
        template_image_url = m.attachments[0].url
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
        template_embed = discord.Embed(
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


def setup(client):
    client.add_cog(Template(client))
