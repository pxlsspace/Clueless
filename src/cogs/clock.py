import disnake
import traceback
from PIL import Image
from sys import stderr
from disnake.ext import commands, tasks
from datetime import datetime, timedelta, timezone

from utils.discord_utils import image_to_file
from utils.setup import stats, db_stats, db_servers, db_users, ws_client, db_templates
from utils.time_converter import local_to_utc
from main import tracked_templates


class Clock(commands.Cog):
    """A class used to manage background periodic tasks.

    It is used to update the stats object periodically."""

    def __init__(self, client: commands.Bot):
        self.client: commands.Bot = client
        self.update_stats.start()
        self.update_online_count.start()

    def cog_unload(self):
        self.update_stats.cancel()
        self.update_online_count.cancel()

    @tasks.loop(seconds=60)
    async def update_stats(self):
        now = datetime.now()
        min = now.strftime("%M")
        if min in ["01", "16", "31", "46"]:
            try:
                await self._update_stats_data()
            except Exception as error:
                formatted = "".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                )
                print("Unexpected exception in task 'update_stats':")
                print(formatted, file=stderr)

    @update_stats.error
    async def update_stats_error(self, error):
        formatted = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        print("Unexpected exception in task 'update_stats':")
        print(formatted, file=stderr)

    # wait for the bot to be ready before starting the task
    @update_stats.before_loop
    async def before_update_stats(self):
        await self.client.wait_until_ready()
        try:
            # update the data on startup
            await self._update_stats_data()

            # load the templates from the database
            canvas_code = await stats.get_canvas_code()
            app_info = await self.client.application_info()
            await tracked_templates.load_all_templates(canvas_code)
            bot_owner_id = app_info.owner.id
            tracked_templates.bot_owner_id = bot_owner_id

            # initialise the combo
            bot_id = app_info.id
            tracked_templates.update_combo(bot_id, canvas_code)

        except Exception as error:
            formatted = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            print("Unexpected error before starting task 'update_stats':")
            print(formatted, file=stderr)

        # start the websocket to update the board
        ws_client.start()

        # wait for the time to be a round value
        round_minute = datetime.now(timezone.utc) + timedelta(minutes=1)
        round_minute = round_minute.replace(second=0, microsecond=0)
        await disnake.utils.sleep_until(round_minute)

    async def _update_stats_data(self):
        # refreshing stats json
        await stats.refresh()
        if stats.stats_json is None:
            now = datetime.now().strftime("[%H:%M:%S]")
            print(now + ": stats page unreachable")
            return

        # create a record for the current time and canvas
        record_id = await self.create_record()
        if record_id is None:
            # there is already a record saved for the current time
            await self.update_boards()
            return

        # save the new stats data in the database
        await self.save_stats(record_id)

        # check on update for the palette
        palette = stats.get_palette()
        canvas_code = await stats.get_canvas_code()
        await db_stats.save_palette(palette, canvas_code)

        ws_client.pause()

        # update the board
        await self.update_boards()

        # save the color stats
        await self.save_color_stats(record_id)

        ws_client.resume()

        # check milestones
        await self.check_milestones()

        # send snapshots
        await self.send_snapshots()

        now = datetime.now().strftime("[%H:%M:%S]")
        print(now + ": stats updated")

    @commands.command(hidden=True)
    @commands.is_owner()
    async def forceupdate(self, ctx):
        try:
            await self._update_stats_data()
        except Exception as e:
            return await ctx.send(
                f"❌ **An error occured during the update:**\n ```{type(e).__name__}: {e}```"
            )
        await ctx.send("✅ Successfully updated stats")

    @tasks.loop(minutes=5)
    async def update_online_count(self):
        # save online count
        try:
            await self.save_online_count()
        except Exception as error:
            formatted = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            print("Unexpected exception in task 'save_online_count':")
            print(formatted, file=stderr)
        # update template stats
        try:
            await self.update_template_stats()
        except Exception as error:
            formatted = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            print("Unexpected exception in task 'update_template_stats':")
            print(formatted, file=stderr)

    @update_online_count.before_loop
    async def before_update_online_count(self):
        time_interval = 5  # minutes
        # wait for the bot to be ready
        await self.client.wait_until_ready()
        # wait that the time is a round value
        now = datetime.now(timezone.utc)
        next_run = now.replace(
            minute=int(now.minute / time_interval) * time_interval,
            second=0,
            microsecond=0,
        ) + timedelta(minutes=time_interval)
        await disnake.utils.sleep_until(next_run)

    async def check_milestones(self):
        """Send alerts in all the servers following a user if they hit a milestone."""

        users_servers = await db_users.get_all_tracked_users()

        for user_id in users_servers.keys():
            values = await db_stats.get_last_two_alltime_counts(user_id)
            if values is None:
                continue
            username = values[0]
            new_count = values[1]
            old_count = values[2]

            if new_count % 1000 < old_count % 1000:
                servers = users_servers[user_id]
                for server_id in servers:
                    channel_id = await db_servers.get_alert_channel(server_id)
                    try:
                        channel = self.client.get_channel(int(channel_id))
                        await channel.send(
                            "New milestone for **"
                            + username
                            + "**! New count: "
                            + str(new_count)
                        )
                    except Exception:
                        pass

    async def send_snapshots(self):
        """Send snapshots for the servers where a channel is set"""
        channels = await db_servers.get_all_snapshots_channels()
        if channels:
            array = stats.palettize_array(stats.board_array)
            board_img = Image.fromarray(array)
            filename = f"snapshot_{datetime.now(timezone.utc).strftime('%FT%H%M')}.png"

        for channel_id in channels:
            try:
                channel = self.client.get_channel(int(channel_id))
                embed = disnake.Embed(title="Canvas Snapshot", color=0x66C5CC)
                embed.timestamp = datetime.now(timezone.utc)
                file = image_to_file(board_img, filename, embed)
                await channel.send(file=file, embed=embed)
            except Exception:
                pass

    async def create_record(self):
        # get the 'last updated' datetime and its timezone
        lastupdated_string = stats.get_last_updated()
        lastupdated = stats.last_updated_to_date(lastupdated_string)
        # Convert /stats to a naive datetime in UTC
        lastupdated = local_to_utc(lastupdated)
        lastupdated = lastupdated.replace(tzinfo=None)  # timezone naive as UTC

        # get the current canvas code
        canvas_code = await stats.get_canvas_code()

        return await db_stats.create_record(lastupdated, canvas_code)

    async def save_stats(self, record_id):
        """Update the database with the new /stats data."""

        # get all the stats
        alltime_stats = stats.get_all_alltime_stats()
        canvas_stats = stats.get_all_canvas_stats()

        await db_stats.update_all_pxls_stats(alltime_stats, canvas_stats, record_id)

    async def save_color_stats(self, record_id):
        # get the board with the placeable pixels only
        placeable_board = await stats.get_placable_board()
        placeable_board_img = Image.fromarray(placeable_board)
        board_colors = placeable_board_img.getcolors()

        # use the virgin map as a mask to get the board with placed pixels
        virgin_array = stats.virginmap_array
        placed_board = placeable_board.copy()
        placed_board[virgin_array != 0] = 255
        placed_board[virgin_array == 0] = placeable_board[virgin_array == 0]
        placed_board_img = Image.fromarray(placed_board)
        placed_colors = placed_board_img.getcolors()

        # Make a dictionary with the color index as key and a dictionnary of
        # amount and amount_placed as value
        colors_dict = {}
        for color_index, color in enumerate(stats.get_palette()):
            colors_dict[color_index] = {}
            colors_dict[color_index]["amount"] = 0
            colors_dict[color_index]["amount_placed"] = 0

        # add board values
        for color in board_colors:
            amount = color[0]
            color_id = color[1]
            if color_id in colors_dict:
                colors_dict[color_id]["amount"] = amount

        # add placed board values
        for color in placed_colors:
            amount = color[0]
            color_id = color[1]
            if color_id in colors_dict:
                colors_dict[color_id]["amount_placed"] = amount

        await db_stats.save_color_stats(colors_dict, record_id)

    async def save_online_count(self):
        """save the current 'online count' in the database"""
        online = stats.online_count
        await stats.update_online_count(online)

    async def update_boards(self):
        # update the canvas boards
        await stats.fetch_board()
        await stats.fetch_virginmap()
        await stats.fetch_placemap()

    async def update_template_stats(self):
        """Update all the tracked templates"""
        canvas_code = await stats.get_canvas_code()
        dt = datetime.utcnow()
        dt = dt.replace(microsecond=0)
        for temp in tracked_templates.list[:]:
            if canvas_code is not None and temp.canvas_code != canvas_code:
                name = temp.name
                # await db_templates.delete_template(temp)
                tracked_templates.list.remove(temp)
                print(f"template '{name}' deleted")
                continue
            progress = temp.update_progress()
            await db_templates.create_template_stat(temp, dt, progress)
        # update the combo and save its progress
        tracked_templates.update_combo(self.client.user.id, canvas_code)
        combo_progress = tracked_templates.combo.update_progress()
        if await db_templates.create_combo_stat(tracked_templates.combo, dt, combo_progress) is None:
            print("Warning: combo stats could not saved.")


def setup(client: commands.Bot):
    client.add_cog(Clock(client))
