from disnake.ext import commands
from utils.setup import db_servers


class Snapshots(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.group(
        hidden=True,
        usage="[setchannel|disable]",
        description="Send canvas snapshots in a channel every 15min.",
        aliases=["snapshot"],
        invoke_without_command=True,
    )
    async def snapshots(self, ctx, args=None):
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
                + ">.\nUse `>snapshots disable` to disable them."
            )

    @snapshots.command(
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
                    f"❌ No snapshots channel set\n (use `{ctx.prefix}snapshots setchannel <#channel|here|none>`)"
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

    @snapshots.command(description="Disable snapshots.", aliases=["unset"])
    @commands.check_any(
        commands.is_owner(), commands.has_permissions(manage_channels=True)
    )
    async def disable(self, ctx):
        await db_servers.update_snapshots_channel(ctx.guild.id, None)
        await ctx.send("✅ Snapshots won't be sent anymore.")


def setup(bot: commands.Bot):
    bot.add_cog(Snapshots(bot))
