from discord.ext import commands
from utils.database import *
from utils.setup import stats
class PxlsMilestones(commands.Cog):

    def __init__(self,client):
        self.client = client
        self.stats = stats

    @commands.group(
        usage = "[add|remove|list|channel|setchannel]",
        description = "Track pxls users milestones.",
        aliases = ["ms"],
        invoke_without_command = True)
    async def milestones(self,ctx,args):
        return
    
    @milestones.command(
        usage = "<name>",
        description = "Add a user to the tracker."
    )
    async def add(self,ctx,name=None):
        # checking valid paramter
        if name == None:
            return await ctx.send("❌ You need to specify a username.")

        # checking if the user exists
        count = self.stats.get_alltime_stat(name)
        if count == None:
            await ctx.send("❌ User not found.")
            return

        if (add_user(ctx.guild.id,name,count)) == -1:
            await ctx.send("❌ This user is already being tracked.")
            return
        msg = "✅ Tracking "+name+"'s all-time counter."
        
        if get_alert_channel(ctx.guild.id) == None:
            msg += f"\nYou haven't set any alert channel, use `>milestones channel [#channel|here]`"
        await ctx.send (msg)
    @milestones.command(
        usage = "<name>",
        description = "Remove a user from the tracker.",
        aliases=["delete","rm"]
        )
    async def remove(self,ctx,name=None):
        if name == None:
            return await ctx.send("❌ You need to specify a username.")
        if(remove_user(ctx.guild.id,name) != -1):
            return await ctx.send ("✅ "+name+" isn't being tracked anymore.")
        else:
            return await ctx.send("❌ User not found.")

    @milestones.command(
        description="Shows the list of users being tracked.",
        aliases=["ls"])
    async def list(self,ctx):
        users = get_all_server_users(ctx.guild.id)
        if len(users) == 0:
            await ctx.send("❌ No user added yet.\n*(use `"+ctx.prefix+"milestones add <username>` to add a new user.*)")
            return
        text="**List of users tracked:**\n"
        for u in users:
            text+="\t- **"+u[0]+":** "+str(u[1])+" pixels\n"
        await ctx.send(text)

    @milestones.command(
        usage = "[#channel|here|none]",
        description = "Set or show the milestone alerts channel",
        aliases=["setchannel"],
        help = """- `[#<channel>]`: set the alerts in the given channel
                  - `[here]`: set the alerts in the current channel
                  - `[none]`: disable the alerts
                If no parameter is given, will show the current alert channel""")
    @commands.has_permissions(manage_channels=True)
    async def channel(self,ctx,channel=None):
        if channel == None:
            # displays the current channel if no argument specified
            channel_id = get_alert_channel(ctx.guild.id)
            if channel_id == None:
                return await ctx.send(f"❌ No alert channel set\n (use `{ctx.prefix}milestones setchannel <#channel|here|none>`)")
            else:
                return await ctx.send("Milestones alerts are set to <#"+str(channel_id)+">")
            #return await ctx.send("you need to give a valid channel")
        channel_id = 0
        if len(ctx.message.channel_mentions) == 0:
            if channel == "here":
                channel_id = ctx.message.channel.id
            elif channel == "none":
                update_alert_channel(None,ctx.guild.id)
                await ctx.send("✅ Miletone alerts won't be sent anymore.")
                return
            else:
                return await ctx.send("❌ You need to give a valid channel.")
        else: 
            channel_id = ctx.message.channel_mentions[0].id

        # checks if the bot has write perms in the alert channel
        channel = self.client.get_channel(channel_id)
        if not ctx.message.guild.me.permissions_in(channel).send_messages:
            await ctx.send(f"❌ I don't not have permissions to send mesages in <#{channel_id}>")
        else:
            # saves the new channel id in the db
            update_alert_channel(channel_id,ctx.guild.id)
            await ctx.send("✅ Milestones alerts successfully set to <#"+str(channel_id)+">")

def setup(client):
    client.add_cog(PxlsMilestones(client))