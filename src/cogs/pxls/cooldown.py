from datetime import datetime

import disnake
from disnake.ext import commands

from utils.discord_utils import format_table
from utils.pxls.cooldown import get_cds, time_convert
from utils.setup import stats


class PxlsCooldown(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot: commands.Bot = bot

    @commands.slash_command(name="cooldown")
    async def _cooldown(
        self,
        inter: disnake.AppCmdInter,
        users: int = commands.Param(ge=0, default=None),
        cd_mult: float = commands.Param(ge=0, default=None, name="cooldown-multiplier"),
    ):
        """Show the current pxls cooldown.

        Parameters
        ----------
        users: The number of users to see the cooldown for.
        cd_mult: The cooldown multiplier (useful to change for cd events).
        """
        await self.cooldown(inter, users, cd_mult)

    @commands.command(
        usage="[nb user] [cooldown multiplier]",
        description="Show the current pxls cooldown.",
        aliases=["cd", "timer"],
    )
    async def cooldown(self, ctx, number=None, cd_mult=None):
        if number is not None:
            try:
                online = int(number)
            except ValueError:
                return await ctx.send("❌ The number of users must be an integer.")
            if online < 0:
                return await ctx.send("❌ The number of users must be positive.")
        else:
            online = stats.online_count
            if online is None:
                return await ctx.send(":x: Current online count unreachable.")

        if cd_mult:
            try:
                multiplier = float(cd_mult)
            except Exception:
                return await ctx.send(":x: The multiplier must be a valid float.")
        else:
            multiplier = stats.get_cd_multiplier()
        multipler_text = (
            f"Cooldown Multiplier: `{multiplier}` " if multiplier != 1 else ""
        )
        desc = multipler_text
        desc += "```JSON\n"

        cooldowns = get_cds(online, multiplier)
        cd_table = []
        total = 0
        for i, total in enumerate(cooldowns):
            if i == 0:
                cd = time_convert(total)
            else:
                cd = time_convert(total - cooldowns[i - 1])
            cd_table.append([f"{i+1}/6", cd, time_convert(total)])

        desc += format_table(cd_table, ["Stack", "Cooldown", "Total"], ["^", "^", "^"])
        desc += "```"

        embed = disnake.Embed(
            color=0x66C5CC,
            title=f"Pxls cooldown for `{online}` user{'s' if online != 1 else ''}",
            description=desc,
        )
        embed.timestamp = datetime.utcnow()
        await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(PxlsCooldown(bot))
