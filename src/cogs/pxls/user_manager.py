import discord
from discord.ext import commands

from utils.discord_utils import UserConverter
from utils.image.image_utils import hex_str_to_int
from utils.setup import db_users
from utils.plot_utils import get_theme, theme_list

class UserManager(commands.Cog):

    def __init__(self,client) -> None:
        self.client = client

    @commands.command(description = "Link your discord account to a pxls username.",usage="<pxls username>")
    async def setname(self,ctx,username):
        pxls_user_id = await db_users.get_pxls_user_id(username)
        if pxls_user_id == None:
            return await ctx.send("❌ Can't find this pxls username.")
        await db_users.set_pxls_user(ctx.author.id,pxls_user_id)
        await ctx.send(f"✅ Pxls username successfully set to **{username}**.")

    @commands.command(description = "Unlink your discord account from a pxls username.")
    async def unsetname(self,ctx):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        if discord_user["pxls_user_id"] == None:
            return await ctx.send("❌ You haven't set any pxls username.")
        await db_users.set_pxls_user(ctx.author.id,None)
        await ctx.send("✅ Pxls username successfully unset.")

    @commands.command(description = "Set your theme for the graphs",
        usage="[theme name]")
    async def theme(self,ctx,theme=None):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        current_user_theme = discord_user["color"] or "default"

        available_themes_text = "**Available themes:**\n"
        for t in theme_list:

            available_themes_text+= "{1} `{0.name}`: {0.description}\n"\
                .format(t,"✓" if t.name == current_user_theme else "☐")

        if theme == None:
            set_theme_text = "*Use `{0}{1.name} {1.usage}` to change your theme.*"\
                .format(ctx.prefix,ctx.command)
            return await ctx.send(available_themes_text + set_theme_text)

        if not theme in [t.name for t in theme_list]:
            error_msg = "❌ Can't find this theme.\n"
            return await ctx.send(error_msg + available_themes_text)

        await db_users.set_user_theme(ctx.author.id,theme)
        await ctx.send(f"✅ Theme successfully set to **{theme}**.")

    @commands.command(
        usage = "[discord name]",
        aliases = ["whois"],
        description="Show your or anyone's pxls username and theme.")
    async def whoami(self,ctx,user=None):

        if user:
            # check that the user exishts
            try:
                user = await UserConverter().convert(ctx,user)
                title = f"🤔 Who is {user.name}?"
            except commands.UserNotFound as e:
                return await ctx.send(f"❌ {e}")
        else:
            user = ctx.author
            title = "🤔 Who am I?"
            
        discord_user = await db_users.get_discord_user(user.id)

        # get the pxls username
        if discord_user["pxls_user_id"] == None:
            pxls_username = f"*Not set\n\t(use `{ctx.prefix}setname <pxls username>`)*"
        else:
            pxls_username = await db_users.get_pxls_user_name(discord_user["pxls_user_id"])
        
        # get the user theme
        user_theme = discord_user["color"] or "default"

        color = get_theme(user_theme).get_palette(1)[0]
        color = hex_str_to_int(color)
        text = f"• **Discord name:** {user}\n"
        text += f"• **Graph theme:** {user_theme}\n"
        text += f"• **Pxls username:** {pxls_username}"
        embed = discord.Embed(title=title,description=text,color=color)
        embed.set_thumbnail(url=user.avatar_url)
        await ctx.send(embed=embed)

def setup(client):
    client.add_cog(UserManager(client))