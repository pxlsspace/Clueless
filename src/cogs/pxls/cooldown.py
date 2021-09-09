from discord.ext import commands
from datetime import datetime
import discord
from discord_slash import cog_ext, SlashContext
from discord_slash.utils.manage_commands import create_option

from utils.pxls.cooldown import get_cds, time_convert
from utils.discord_utils import format_table
from utils.setup import stats, GUILD_IDS

class PxlsCooldown(commands.Cog):

    def __init__(self,client):
        self.client = client

    @cog_ext.cog_slash(name="cooldown",
        description="Show the current pxls cooldown.",
        guild_ids=GUILD_IDS,
        options=[
        create_option(
            name="users",
            description="The number of users to see the cooldown for.",
            option_type=3,
            required=False
        )]
    )
    async def _cooldown(self,ctx:SlashContext, users=None):
        await self.cooldown(ctx,users)

    @commands.command(
        usage ="[nb user]",
        description = "Show the current pxls cooldown.",
        aliases = ["cd","timer"])
    async def cooldown(self,ctx,number=None):
        if number:
            online = int(number)
        else:
            online = stats.online_count

        total = 0
        cooldowns = get_cds(online)

        cd_table = []
        desc = "```JSON\n"
        for i,total in enumerate(cooldowns):
            if i == 0:
                cd = time_convert(total)
            else:
                cd = time_convert(total-cooldowns[i-1])
            cd_table.append([f'{i+1}/6',cd,time_convert(total)])
        
        desc += format_table(cd_table,["Stack","Cooldown","Total"],["^","^","^"])
        desc += "```"

        embed = discord.Embed(
            color=0x66c5cc,
            title=f"Pxls cooldown for `{online}` users",
            description=desc
        )
        embed.timestamp = datetime.utcnow()
        await ctx.send(embed=embed)

def setup(client):
    client.add_cog(PxlsCooldown(client))