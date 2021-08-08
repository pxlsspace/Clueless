import discord
from discord.ext import commands
from discord.ext.commands.converter import RoleConverter
from discord.ext.commands.errors import RoleNotFound

from utils.setup import db_users_manager as db_users, db_servers_manager as db_servers
from utils.discord_utils import UserConverter

class Blacklist(commands.Cog):
    
    def __init__(self,client) -> None:
        self.client = client

    @commands.group(hidden=True,description="Ban a user from using the bot.")
    @commands.is_owner()
    async def blacklist(self,ctx):
        pass

    @blacklist.command(name="add",description="Add a user to the blacklist.",usage="<user>")
    async def blacklist_add(self,ctx,user):
       # check that the user exists
        try:
            user = await UserConverter().convert(ctx,user)
        except commands.UserNotFound as e:
            return await ctx.send(f"❌ {e}")

        # check that the user isn't the bot owner
        app_info = await self.client.application_info()
        owner = app_info.owner
        if user == owner:
            return await ctx.send(f"❌ You can't blacklist the bot owner.")

        # check that the user isn't already blacklisted
        no_user_mention = discord.AllowedMentions(users=False) # to avoid pinging user
        discord_db_user = await db_users.get_discord_user(user.id)
        if discord_db_user["is_blacklisted"] == True:
            return await ctx.send("❌ <@{}> is already blacklisted.".format(user.id),allowed_mentions=no_user_mention)

        # add to the blacklist
        await db_users.set_user_blacklist(user.id,True)
        return await ctx.send("✅ <@{}> has been blacklisted.".format(user.id),allowed_mentions=no_user_mention)

    @blacklist.command(name="remove",description="Remove a user from the blacklist.",usage="<user>",aliases =["rm"])
    async def blacklist_remove(self,ctx,user):
        # check that the user exists
        try:
            user = await UserConverter().convert(ctx,user)
        except commands.UserNotFound as e:
            return await ctx.send(f"❌ {e}")
        
        # check that the user is actually blacklisted
        no_user_mention = discord.AllowedMentions(users=False) # to avoid pinging user
        discord_db_user = await db_users.get_discord_user(user.id)
        if discord_db_user["is_blacklisted"] == False:
            return await ctx.send("❌ <@{}> is not blacklisted.".format(user.id),allowed_mentions=no_user_mention)

        # remove from the blacklist
        await db_users.set_user_blacklist(user.id,False)
        return await ctx.send("✅ <@{}> has been removed from the blacklis.".format(user.id),allowed_mentions=no_user_mention)

    @blacklist.command(description="Show all the blacklisted users.",aliases =["ls"])
    async def list(self,ctx):
        blacklisted_users = await db_users.get_all_blacklisted_users()
        if blacklisted_users == None:
            return await ctx.send("**No users are blacklisted.**")
        else:
            text = "**Blacklisted users:**\n"
            for user_id in blacklisted_users:
                text+="\t• <@{}>\n".format(user_id)
            no_user_mention = discord.AllowedMentions(users=False) # to avoid pinging user
            await ctx.send(text,allowed_mentions=no_user_mention)

    @commands.group(hidden=True,invoke_without_command=True,description = "Show the current blacklist role.")
    @commands.check_any(commands.is_owner(),commands.has_permissions(manage_roles=True))
    async def roleblacklist(self,ctx):
        # show the current role
        current_role_id = await db_servers.get_blacklist_role(ctx.guild.id)
        if current_role_id == None:
            return await ctx.send(f"No blacklist role assigned, use `{ctx.prefix}{ctx.command} add <role>`")
        current_role = ctx.guild.get_role(int(current_role_id))
        if current_role == None:
            return await ctx.send(f"The current blacklist role is invalid, use `{ctx.prefix}{ctx.command} <role>`")
        else:
            no_role_mention = discord.AllowedMentions(roles=False) # to avoid pinging when showing the role
            return await ctx.send(f"Current blacklist role: <@&{current_role.id}>.",allowed_mentions=no_role_mention)

    @roleblacklist.command(
        description = "Add a blacklist role, any user with this role won't be able to use the bot.",
        usage = "<role name|role id|@role>"
        )
    async def add(self,ctx,role):
        # check that the role exists and save it
        try:
            role = await RoleConverter().convert(ctx,role)
        except RoleNotFound as e:
            return await ctx.send(f"❌ {e}")
        await db_servers.update_blacklist_role(ctx.guild.id,role.id)
        no_role_mention = discord.AllowedMentions(roles=False) # to avoid pinging when showing the role
        await ctx.send(f"✅ Blacklist role set to <@&{role.id}>.",allowed_mentions=no_role_mention)

    @roleblacklist.command(description = "Remove the current blacklist role.")
    async def remove(self,ctx):
        await db_servers.update_blacklist_role(ctx.guild.id,None)
        await ctx.send("✅ Blacklist role removed.")

def setup(client):
    client.add_cog(Blacklist(client))