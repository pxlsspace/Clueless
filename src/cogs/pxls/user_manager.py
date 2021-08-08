from discord.ext import commands

from utils.setup import db_users_manager as db_users
class UserManager(commands.Cog):

    def __init__(self,client) -> None:
        self.client = client

    @commands.command(description = "Link your discord account to a pxls username.",usage="<pxls username>")
    async def setname(self,ctx,pxls_name):
        pxls_user_id = await db_users.get_pxls_user_id(pxls_name)
        if pxls_user_id == None:
            return await ctx.send("❌ Can't find this pxls user name.")
        await db_users.set_pxls_user(ctx.author.id,pxls_user_id)
        await ctx.send(f"✅ Pxls username succefully set to **{pxls_name}**.")

    @commands.command(description = "Unlink your discord account from a pxls username.")
    async def unset(self,ctx):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        if discord_user["pxls_user_id"] == None:
            return await ctx.send("❌ You haven't set any pxls username.")
        await db_users.set_pxls_user(ctx.author.id,None)
        await ctx.send("✅ Pxls username succefully unset.")

    @commands.command(description="Show the pxls username linked to your account.")
    async def whoami(self,ctx):
        discord_user = await db_users.get_discord_user(ctx.author.id)
        if discord_user["pxls_user_id"] == None:
            return await ctx.send(f"❌ You haven't set your pxls username, use `{ctx.prefix}setname <pxls_username>`")
        pxls_username = await db_users.get_pxls_user_name(discord_user["pxls_user_id"])
        await ctx.send(f"Your pxls username is set to **{pxls_username}**.")

def setup(client):
    client.add_cog(UserManager(client))