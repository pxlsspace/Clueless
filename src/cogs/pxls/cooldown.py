from discord.ext import commands
import discord
from utils.pxls.cooldown import get_cds, time_convert
from utils.discord_utils import format_table
from utils.setup import stats

class PxlsCooldown(commands.Cog):

    def __init__(self,client):
        self.client = client

    @commands.command(
        usage ="[nb user]",
        description = "Show the current pxls cooldown.",
        aliases = ["cd","timer"])
    async def cooldown(self,ctx,number=None):
        if number:
            online = int(number)
        else:
            online = await stats.get_online_count()

        i = 0
        total = 0
        cooldowns = get_cds(online)

        cd_table = []
        desc = "```\n"
        for cd in cooldowns:
            i+=1
            total += cd
            cd_table.append([f'• {i}/6',time_convert(cd),time_convert(total)])
        
        desc += format_table(cd_table,["stack","cd","total"])
        desc += "```"
        embed = discord.Embed(title=f"Pxls cooldown for `{online}` users",description=desc)
        await ctx.send(embed=embed)

def setup(client):
    client.add_cog(PxlsCooldown(client))