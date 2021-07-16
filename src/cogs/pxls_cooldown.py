from discord.ext import commands
import discord
import requests
import json
from utils.cooldown import get_cds, time_convert
from utils.discord_utils import format_table

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
            r = requests.get('https://pxls.space/users')
            online = json.loads(r.text)["count"]

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
        #embed.add_field(name=dash,value=text)
        await ctx.send(embed=embed)

def setup(client):
    client.add_cog(PxlsCooldown(client))