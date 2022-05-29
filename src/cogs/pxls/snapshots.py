import re
from io import BytesIO
from PIL import Image
from datetime import datetime, timezone, timedelta
import disnake
from disnake.ext import commands
from utils.arguments_parser import MyParser, valid_datetime_type
from utils.discord_utils import AuthorView, get_urls_from_list, image_to_file
from utils.image.image_utils import find_upscale
from utils.pxls.template_manager import get_template_from_url, parse_template
from utils.setup import db_servers, db_users, db_stats, stats
from utils.timezoneslib import get_timezone
from utils.time_converter import format_datetime, str_to_td, td_format
from utils.utils import get_content
from main import tracked_templates


class SnapshotButton(disnake.ui.Button):
    def __init__(self, td: timedelta, coords: list, upscale: bool):
        self.td = td
        self.coords = coords
        self.upscale = upscale
        if td < timedelta(hours=0):
            label = "-" + td_format(abs(self.td), short_format=True)
        else:
            label = "+" + td_format(self.td, short_format=True)
        super().__init__(style=disnake.ButtonStyle.gray, label=label)

    async def callback(self, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        dt = self.view.dt + self.td
        await Snapshots.snapshot(
            interaction,
            dt.strftime("%Y-%m-%d %H:%M"),
            coords=self.coords,
            message=self.view.message,
            view=self.view,
            upscale=self.upscale,
        )


class SnapshotView(AuthorView):
    message: disnake.Message

    def __init__(
        self,
        author: disnake.User,
        dt: datetime,
        coords: list,
        snapshot_image: Image.Image,
    ):
        self.dt = dt
        self.coords = coords
        self.snapshot_image = snapshot_image
        self.snapshot_image_upscaled = None

        self.btn_state = 0
        self.upscale_state = 0
        super().__init__(author)

        timedeltas1 = [
            timedelta(hours=-1),
            timedelta(minutes=-15),
            timedelta(minutes=15),
            timedelta(hours=1),
        ]
        timedeltas2 = [
            timedelta(days=-1),
            timedelta(hours=-12),
            timedelta(hours=12),
            timedelta(days=1),
        ]

        self.timedeltas = [timedeltas1, timedeltas2]
        self.remove_item(self.switch)
        self.remove_item(self.upscale)
        for td in self.timedeltas[self.btn_state]:
            btn = SnapshotButton(td, coords, self.upscale_state)
            self.add_item(btn)
        self.children.insert(2, self.switch)
        if self.snapshot_image and find_upscale(self.snapshot_image) > 1:
            self.upscale.label = "Downscale" if self.upscale_state else "Upscale"
            self.upscale.row = 1
            self.add_item(self.upscale)

    async def on_timeout(self) -> None:
        for c in self.children[:]:
            self.remove_item(c)
        await self.message.edit(view=self)

    def update(self, dt, upscale, snapshot_image, snapshot_image_upscaled):
        self.dt = dt
        self.upscale_state = int(upscale)
        self.upscale.label = "Downscale" if self.upscale_state else "Upscale"
        self.snapshot_image = snapshot_image
        self.snapshot_image_upscaled = snapshot_image_upscaled

    @disnake.ui.button(
        emoji="<:refresh:976870681729962017>", style=disnake.ButtonStyle.blurple
    )
    async def switch(self, button, inter: disnake.MessageInteraction):
        self.btn_state = 1 - self.btn_state
        for c in self.children[:]:
            self.remove_item(c)
        for td in self.timedeltas[self.btn_state]:
            btn = SnapshotButton(td, self.coords, self.upscale_state)
            self.add_item(btn)
        self.children.insert(2, self.switch)
        if self.snapshot_image and find_upscale(self.snapshot_image) > 1:
            self.upscale.label = "Downscale" if self.upscale_state else "Upscale"
            self.add_item(self.upscale)
        await inter.response.edit_message(view=self)

    @disnake.ui.button(label="Upscale", style=disnake.ButtonStyle.blurple)
    async def upscale(self, button, inter: disnake.MessageInteraction):
        await inter.response.defer()
        if not self.snapshot_image:
            return
        scale = find_upscale(self.snapshot_image)
        if scale == 1:
            return

        if self.upscale_state:
            image = self.snapshot_image
        else:
            if self.snapshot_image_upscaled is None:
                self.snapshot_image_upscaled = self.snapshot_image.resize(
                    (
                        self.snapshot_image.width * scale,
                        self.snapshot_image.height * scale,
                    ),
                    Image.NEAREST,
                )
            image = self.snapshot_image_upscaled

        embed = (await inter.original_message()).embeds[0]
        file = await image_to_file(
            image,
            f"snapshot_{self.dt.strftime('%FT%H%M')}.png",
            embed,
        )
        self.upscale_state = 1 - self.upscale_state
        self.upscale.label = "Downscale" if self.upscale_state else "Upscale"
        for c in self.children:
            if isinstance(c, SnapshotButton):
                c.upscale = self.upscale_state
        await inter.edit_original_message(embed=embed, files=[file], view=self)


class Snapshots(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.group(
        hidden=True,
        usage="[setchannel|disable]",
        description="Send canvas snapshots in a channel every 15min.",
        aliases=["setsnapshot"],
        invoke_without_command=True,
    )
    async def setsnapshots(self, ctx, args=None):
        # display the current channel
        channel_id = await db_servers.get_snapshots_channel(ctx.guild.id)
        if channel_id is None:
            return await ctx.send(
                f"No snapshots channel set.\nYou can enable automatic canvas snapshots every 15 minutes with: `{ctx.prefix}snapshots setchannel <#channel|here|none>`"
            )
        else:
            return await ctx.send(
                "Snapshots are set to <#"
                + str(channel_id)
                + ">.\nUse `>setsnapshot disable` to disable them."
            )

    @setsnapshots.command(
        usage="[#channel|here|none]",
        description="Set the channel for the snapshots.",
        aliases=["setchannel"],
        help="""- `[#<channel>]`: set the snapshots in the given channel
                  - `[here]`: send the snapshots in the current channel
                  - `[none]`: disable the snapshots
                If no parameter is given, will show the current snapshots channel""",
    )
    @commands.is_owner()
    async def channel(self, ctx, channel=None):
        if channel is None:
            # displays the current channel if no argument specified
            channel_id = await db_servers.get_snapshots_channel(ctx.guild.id)
            if channel_id is None:
                return await ctx.send(
                    f"❌ No snapshots channel set\n (use `{ctx.prefix}setsnapshot channel <#channel|here|none>`)"
                )
            else:
                return await ctx.send("Snapshots are set to <#" + str(channel_id) + ">")
            # return await ctx.send("you need to give a valid channel")
        channel_id = 0
        if len(ctx.message.channel_mentions) == 0:
            if channel == "here":
                channel_id = ctx.message.channel.id
            elif channel == "none":
                await db_servers.update_snapshots_channel(ctx.guild.id, None)
                await ctx.send("✅ Snapshots won't be sent anymore.")
                return
            else:
                return await ctx.send("❌ You need to give a valid channel.")
        else:
            channel_id = ctx.message.channel_mentions[0].id

        # checks if the bot has write perms in the snapshots channel
        channel = self.bot.get_channel(channel_id)
        if not channel.permissions_for(ctx.guild.me).send_messages:
            await ctx.send(
                f"❌ I don't have permissions to send messages in <#{channel_id}>"
            )
        else:
            # saves the new channel id in the db
            await db_servers.update_snapshots_channel(ctx.guild.id, channel_id)
            await ctx.send("✅ Snapshots successfully set to <#" + str(channel_id) + ">")

    @setsnapshots.command(description="Disable snapshots.", aliases=["unset"])
    @commands.check_any(
        commands.is_owner(), commands.has_permissions(manage_channels=True)
    )
    async def disable(self, ctx):
        await db_servers.update_snapshots_channel(ctx.guild.id, None)
        await ctx.send("✅ Snapshots won't be sent anymore.")

    @commands.slash_command(name="snapshot")
    async def _snapshot(
        self,
        inter: disnake.AppCmdInter,
        datetime: str = None,
        relative_time: str = commands.Param(default=None, name="relative-time"),
        template=None,
        coords=None,
    ):
        """
        Browse the canvas snapshots.

        Parameters
        ----------
        datetime: The date/time of the snapshot. (format: YYYY-mm-dd HH:MM)
        relative_time: To get the snapshot at a relative time. (i.e. '3d' = 3 days ago) (format: ?d?h?m)
        template: To crop the snapshot in the template area only.
        coords: To crop the snapshot between 2 points. (format: x0 y0 x1 y1)
        """

        if coords:
            coords = re.findall(r"-?\d+", coords)
            if len(coords) != 4:
                return await inter.send(":x: Invalid coords (format: x0 y0 x1 y1)")

        await inter.response.defer()
        await self.snapshot(inter, datetime or relative_time, template, coords)

    @commands.command(
        name="snapshot",
        usage="[datetime|relative time] [template] [-coords x0 y0 x1 y1]",
        description="Browse the canvas snapshots.",
        aliases=["snapshots", "ss"],
        help="""
        `[datetime]`: the date/time of the snapshot (format: YYYY-mm-dd HH:MM)
        `[relative time]`: to get the snapshot at a relative time (i.e. '3d' = 3 days ago) (format: ?d?h?m)
        `[template]`: to crop the snapshot in the template area only
        `[-coords x0 y0 x1 y1]`: to crop the snapshot between 2 points
        """,
    )
    async def p_snapshot(self, ctx, *args):
        parser = MyParser(add_help=False)
        parser.add_argument("args", action="store", nargs="*")
        parser.add_argument(
            "-coords",
            "-crop",
            "-c",
            action="store",
            nargs="+",
            required=False,
            default=None,
        )

        try:
            parsed_args, unknown = parser.parse_known_args(args)
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        dts, urls = get_urls_from_list(parsed_args.args)
        dt = " ".join(dts) if dts else None
        template = urls[0] if urls else None

        if parsed_args.coords:
            coords = " ".join(parsed_args.coords)
            coords = re.findall(r"-?\d+", coords)
        else:
            coords = None
        async with ctx.typing():
            await self.snapshot(ctx, dt, template, coords)

    @staticmethod
    async def snapshot(
        ctx,
        dt=None,
        template_input=None,
        coords: list = None,
        message: disnake.Message = None,
        view: SnapshotView = None,
        upscale=False,
    ):

        # check datetime
        discord_user = await db_users.get_discord_user(ctx.author.id)
        user_timezone = get_timezone(discord_user["timezone"]) or timezone.utc
        if dt is not None:
            try:
                dt = valid_datetime_type(dt, user_timezone)
            except ValueError:
                td = str_to_td(dt)
                if td is None:
                    return await ctx.send(
                        ":x: Invalid datetime, format must be `YYYY-mm-dd HH:MM` or `?d?h?m` (where `?` is a number)."
                    )
                dt = datetime.now(user_timezone) - td

        else:
            dt = datetime.now(user_timezone)

        # check template
        if template_input and not coords:
            template = tracked_templates.get_template(template_input)
            if template is None:
                if parse_template(template_input):
                    try:
                        template = await get_template_from_url(template_input)
                    except ValueError as e:
                        return await ctx.send(f":x: {e}")
                else:
                    return await ctx.send(
                        f"There is no template with the name `{template_input}` in the tracker"
                    )
            coords = [
                template.ox,
                template.oy,
                template.ox + template.width - 1,
                template.oy + template.height - 1,
            ]
        # check coords
        if coords:
            if len(coords) != 4:
                return await ctx.send(":x: Invalid coords (format: x0 y0 x1 y1).")
            try:
                coords = [int(c) for c in coords]
            except ValueError:
                return await ctx.send(":x: coords must be integers.")

        canvas_code = await stats.get_canvas_code()
        snapshot = await db_stats.get_snapshot_at(
            dt.astimezone(timezone.utc).replace(tzinfo=None), canvas_code
        )
        snapshot_dt = snapshot["datetime"].replace(tzinfo=timezone.utc)
        snapshot_url = snapshot["url"]
        embed = disnake.Embed(title="Snapshot", color=0x66C5CC, timestamp=snapshot_dt)
        embed.description = "Date/time: {} ({})".format(
            format_datetime(snapshot_dt),
            format_datetime(snapshot_dt, "R"),
        )

        files = []
        snapshot_image_cropped = None
        snapshot_image_cropped_upscaled = None
        if coords:
            x0, y0, x1, y1 = coords
            snapshot_bytes = await get_content(snapshot_url, "image")
            snapshot_image = Image.open(BytesIO(snapshot_bytes))
            try:
                snapshot_image_cropped = snapshot_image.crop((x0, y0, x1 + 1, y1 + 1))
                snapshot_file = await image_to_file(
                    snapshot_image_cropped,
                    f"snapshot_{snapshot_dt.strftime('%FT%H%M')}.png",
                    embed,
                )
            except Exception:
                return await ctx.send(":x: Invalid coords.")
            files = [snapshot_file]
        else:
            embed.set_image(snapshot_url)

        if upscale:
            scale = find_upscale(snapshot_image_cropped)
            if scale != 1:
                snapshot_image_cropped_upscaled = snapshot_image_cropped.resize(
                    (
                        snapshot_image_cropped.width * scale,
                        snapshot_image_cropped.height * scale,
                    ),
                    Image.NEAREST,
                )
            else:
                snapshot_image_cropped_upscaled = snapshot_image_cropped
            upscaled_file = await image_to_file(
                snapshot_image_cropped_upscaled,
                f"snapshot_{snapshot_dt.strftime('%FT%H%M')}.png",
                embed,
            )
            files = [upscaled_file]

        if message is None:
            view = SnapshotView(
                ctx.author,
                snapshot_dt.astimezone(user_timezone),
                coords,
                snapshot_image_cropped,
            )
            m = await ctx.send(embed=embed, view=view, files=files)
            if m is None:
                m = await ctx.original_message()
            view.message = m
        else:
            view.update(
                snapshot_dt.astimezone(user_timezone),
                upscale,
                snapshot_image_cropped,
                snapshot_image_cropped_upscaled,
            )
            await message.edit(embed=embed, view=view, files=files)


def setup(bot: commands.Bot):
    bot.add_cog(Snapshots(bot))
