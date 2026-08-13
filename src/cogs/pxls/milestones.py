from sqlite3 import IntegrityError

import disnake
from disnake.ext import commands

from utils.setup import db_servers, db_users


class PxlsMilestones(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.group(
        hidden=True,
        usage="[add|remove|list|channel|setchannel]",
        description="Track pxls users milestones.",
        aliases=["ms"],
        invoke_without_command=True,
    )
    @commands.has_permissions(manage_channels=True)
    async def milestones(self, ctx, args):
        return

    @milestones.command(usage="<name>", description="Add a user to the tracker.")
    async def add(self, ctx, name=None):
        # checking valid paramter
        if name is None:
            return await ctx.send("❌ You need to specify a username.")

        try:
            await db_users.create_server_pxls_user(ctx.guild.id, name)
        except IntegrityError:
            return await ctx.send("❌ This user is already being tracked.")
        except ValueError:
            return await ctx.send("❌ User not found.")

        msg = "✅ Tracking " + name + "'s all-time counter."

        if await db_servers.get_alert_channel(ctx.guild.id) is None:
            msg += "\nYou haven't set any alert channel, use `>milestones channel [#channel|here]`"
        await ctx.send(msg)

    @milestones.command(
        usage="<name>",
        description="Remove a user from the tracker.",
        aliases=["delete", "rm"],
    )
    async def remove(self, ctx, name=None):
        if name is None:
            return await ctx.send("❌ You need to specify a username.")
        try:
            await db_users.delete_server_pxls_user(ctx.guild.id, name) != -1
        except ValueError as e:
            return await ctx.send(f"❌ {e}")
        return await ctx.send("✅ " + name + " isn't being tracked anymore.")

    @milestones.command(
        description="Shows the list of users being tracked.", aliases=["ls"]
    )
    async def list(self, ctx):
        users = await db_users.get_all_server_tracked_users(ctx.guild.id)
        if len(users) == 0:
            await ctx.send(
                "❌ No user added yet.\n*(use `/milestones add <username>` to add a new user.*)"
            )
            return
        text = "**List of users tracked:**\n"
        for u in users:
            text += "\t- **" + u[0] + ":** " + str(u[1]) + " pixels\n"
        await ctx.send(text)

    @milestones.command(
        usage="[#channel|here|none]",
        description="Set or show the milestone alerts channel",
        aliases=["setchannel"],
        help="""- `[#<channel>]`: set the alerts in the given channel
                  - `[here]`: set the alerts in the current channel
                  - `[none]`: disable the alerts
                If no parameter is given, will show the current alert channel""",
    )
    @commands.has_permissions(manage_channels=True)
    async def channel(self, ctx, channel=None):
        if channel is None:
            # displays the current channel if no argument specified
            return await self._do_set_milestones_channel(ctx, None, False, True)

        if len(ctx.message.channel_mentions) == 0:
            if channel == "here":
                resolved_channel = ctx.message.channel
            elif channel == "none":
                return await self._do_set_milestones_channel(ctx, None, True, False)
            else:
                return await ctx.send("❌ You need to give a valid channel.")
        else:
            resolved_channel = ctx.message.channel_mentions[0]

        await self._do_set_milestones_channel(ctx, resolved_channel, False, False)

    async def _do_set_milestones_channel(self, ctx, channel, disable, show):
        if show:
            # displays the current channel if no argument specified
            channel_id = await db_servers.get_alert_channel(ctx.guild.id)
            if channel_id is None:
                return await ctx.send(
                    "❌ No alert channel set\n (use `/milestones channel <#channel|here|none>`)"
                )
            else:
                return await ctx.send(
                    "Milestones alerts are set to <#" + str(channel_id) + ">"
                )

        if disable:
            await db_servers.update_alert_channel(ctx.guild.id, None)
            await ctx.send("✅ Milestone alerts won't be sent anymore.")
            return

        # checks if the bot has write perms in the alert channel
        if not ctx.guild.me.permissions_in(channel).send_messages:
            await ctx.send(
                f"❌ I do not have permissions to send mesages in <#{channel.id}>"
            )
        else:
            # saves the new channel id in the db
            await db_servers.update_alert_channel(ctx.guild.id, channel.id)
            await ctx.send(
                "✅ Milestones alerts successfully set to <#" + str(channel.id) + ">"
            )

    @commands.slash_command(
        name="milestones",
        default_member_permissions=disnake.Permissions(manage_channels=True),
    )
    async def _milestones(self, inter: disnake.AppCmdInter):
        """Track pxls users milestones."""
        pass  # group root is a no-op

    @_milestones.sub_command(name="add")
    @commands.has_permissions(manage_channels=True)
    async def _milestones_add(self, inter: disnake.AppCmdInter, username: str):
        """Add a user to the tracker.

        Parameters
        ----------
        username: The pxls username to track."""
        await inter.response.defer()
        await self.add(inter, name=username)

    @_milestones.sub_command(name="remove")
    @commands.has_permissions(manage_channels=True)
    async def _milestones_remove(self, inter: disnake.AppCmdInter, username: str):
        """Remove a user from the tracker.

        Parameters
        ----------
        username: The pxls username to stop tracking."""
        await inter.response.defer()
        await self.remove(inter, name=username)

    @_milestones.sub_command(name="list")
    @commands.has_permissions(manage_channels=True)
    async def _milestones_list(self, inter: disnake.AppCmdInter):
        """Shows the list of users being tracked."""
        await inter.response.defer()
        await self.list(inter)

    @_milestones.sub_command(name="channel")
    @commands.has_permissions(manage_channels=True)
    async def _milestones_channel(
        self,
        inter: disnake.AppCmdInter,
        channel: disnake.TextChannel = None,
        disable: bool = False,
    ):
        """Set or show the milestone alerts channel.

        Parameters
        ----------
        channel: The channel to send the milestone alerts to.
        disable: Disable the milestone alerts."""
        await inter.response.defer()
        show = channel is None and not disable
        await self._do_set_milestones_channel(inter, channel, disable, show)


def setup(bot: commands.Bot):
    return  # this command is disabled
    bot.add_cog(PxlsMilestones(bot))
