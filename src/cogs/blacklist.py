import disnake
from disnake.ext import commands
from disnake.ext.commands.converter import RoleConverter
from disnake.ext.commands.errors import RoleNotFound

from utils.discord_utils import UserConverter
from utils.setup import db_servers, db_users, owner_only


class Blacklist(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    @commands.group(hidden=True, description="Ban a user from using the bot.")
    @commands.is_owner()
    async def blacklist(self, ctx):
        pass

    @blacklist.command(
        name="add", description="Add a user to the blacklist.", usage="<user>"
    )
    async def blacklist_add(self, ctx, user):
        # check that the user exists
        try:
            user = await UserConverter().convert(ctx, user)
        except commands.UserNotFound as e:
            return await ctx.send(f"❌ {e}")
        await self._do_blacklist_add(ctx, user)

    async def _do_blacklist_add(self, ctx, user):
        # check that the user isn't the bot owner
        app_info = await self.bot.application_info()
        owner = app_info.owner
        if user == owner:
            return await ctx.send("❌ You can't blacklist the bot owner.")

        # check that the user isn't already blacklisted
        no_user_mention = disnake.AllowedMentions(users=False)  # to avoid pinging user
        discord_db_user = await db_users.get_discord_user(user.id)
        if discord_db_user["is_blacklisted"]:
            return await ctx.send(
                "❌ <@{}> is already blacklisted.".format(user.id),
                allowed_mentions=no_user_mention,
            )

        # add to the blacklist
        await db_users.set_user_blacklist(user.id, True)
        return await ctx.send(
            "✅ <@{}> has been blacklisted.".format(user.id),
            allowed_mentions=no_user_mention,
        )

    @blacklist.command(
        name="remove",
        description="Remove a user from the blacklist.",
        usage="<user>",
        aliases=["rm"],
    )
    async def blacklist_remove(self, ctx, user):
        # check that the user exists
        try:
            user = await UserConverter().convert(ctx, user)
        except commands.UserNotFound as e:
            return await ctx.send(f"❌ {e}")
        await self._do_blacklist_remove(ctx, user)

    async def _do_blacklist_remove(self, ctx, user):
        # check that the user is actually blacklisted
        no_user_mention = disnake.AllowedMentions(users=False)  # to avoid pinging user
        discord_db_user = await db_users.get_discord_user(user.id)
        if not discord_db_user["is_blacklisted"]:
            return await ctx.send(
                "❌ <@{}> is not blacklisted.".format(user.id),
                allowed_mentions=no_user_mention,
            )

        # remove from the blacklist
        await db_users.set_user_blacklist(user.id, False)
        return await ctx.send(
            "✅ <@{}> has been removed from the blacklist.".format(user.id),
            allowed_mentions=no_user_mention,
        )

    @blacklist.command(description="Show all the blacklisted users.", aliases=["ls"])
    async def list(self, ctx):
        blacklisted_users = await db_users.get_all_blacklisted_users()
        if blacklisted_users is None:
            return await ctx.send("**No users are blacklisted.**")
        else:
            text = "**Blacklisted users:**\n"
            for user_id in blacklisted_users:
                text += "\t• <@{}>\n".format(user_id)
            await ctx.send(text)

    @commands.slash_command(name="blacklist")
    async def _blacklist(self, inter: disnake.AppCmdInter):
        """Ban a user from using the bot."""
        pass  # group root is a no-op

    @_blacklist.sub_command(name="add")
    @owner_only()
    async def _blacklist_add(self, inter: disnake.AppCmdInter, user: disnake.User):
        """Add a user to the blacklist.

        Parameters
        ----------
        user: The user to blacklist."""
        await inter.response.defer()
        await self._do_blacklist_add(inter, user)

    @_blacklist.sub_command(name="remove")
    @owner_only()
    async def _blacklist_remove(self, inter: disnake.AppCmdInter, user: disnake.User):
        """Remove a user from the blacklist.

        Parameters
        ----------
        user: The user to remove from the blacklist."""
        await inter.response.defer()
        await self._do_blacklist_remove(inter, user)

    @_blacklist.sub_command(name="list")
    @owner_only()
    async def _blacklist_list(self, inter: disnake.AppCmdInter):
        """Show all the blacklisted users."""
        await inter.response.defer()
        await self.list(inter)

    @commands.group(
        hidden=True,
        invoke_without_command=True,
        description="Show the current blacklist role.",
    )
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_roles=True))
    async def roleblacklist(self, ctx):
        # show the current role
        current_role_id = await db_servers.get_blacklist_role(ctx.guild.id)
        if current_role_id is None:
            return await ctx.send(
                f"No blacklist role assigned, use `{ctx.prefix}{ctx.command} add <role>`"
            )
        current_role = ctx.guild.get_role(int(current_role_id))
        if current_role is None:
            return await ctx.send(
                f"The current blacklist role is invalid, use `{ctx.prefix}{ctx.command} <role>`"
            )
        else:
            return await ctx.send(f"Current blacklist role: <@&{current_role.id}>.")

    @roleblacklist.command(
        description="Add a blacklist role, any user with this role won't be able to use the bot.",
        usage="<role name|role id|@role>",
    )
    async def add(self, ctx, role):
        # check that the role exists and save it
        try:
            role = await RoleConverter().convert(ctx, role)
        except RoleNotFound as e:
            return await ctx.send(f"❌ {e}")
        await self._do_roleblacklist_add(ctx, role)

    async def _do_roleblacklist_add(self, ctx, role):
        await db_servers.update_blacklist_role(ctx.guild.id, role.id)
        await ctx.send(f"✅ Blacklist role set to <@&{role.id}>.")

    @roleblacklist.command(description="Remove the current blacklist role.")
    async def remove(self, ctx):
        await db_servers.update_blacklist_role(ctx.guild.id, None)
        await ctx.send("✅ Blacklist role removed.")

    @commands.slash_command(
        name="roleblacklist",
        default_member_permissions=disnake.Permissions(manage_roles=True),
    )
    async def _roleblacklist(self, inter: disnake.AppCmdInter):
        """Manage the role used to blacklist users from using the bot."""
        pass  # group root is a no-op

    @_roleblacklist.sub_command(name="add")
    @commands.has_permissions(manage_roles=True)
    async def _roleblacklist_add(self, inter: disnake.AppCmdInter, role: disnake.Role):
        """Add a blacklist role, any user with this role won't be able to use the bot.

        Parameters
        ----------
        role: The role to use as the blacklist role."""
        await inter.response.defer()
        await self._do_roleblacklist_add(inter, role)

    @_roleblacklist.sub_command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def _roleblacklist_remove(self, inter: disnake.AppCmdInter):
        """Remove the current blacklist role."""
        await inter.response.defer()
        await self.remove(inter)


def setup(bot: commands.Bot):
    bot.add_cog(Blacklist(bot))
