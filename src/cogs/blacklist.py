import disnake
from disnake import Team
from disnake.ext import commands
from disnake.ext.commands.converter import RoleConverter
from disnake.ext.commands.errors import RoleNotFound

from utils.discord_utils import UserConverter, get_display_prefix
from utils.setup import db_servers, db_users


class Blacklist(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    # --- shared helpers (take a resolved user/role object) ---

    async def _do_blacklist_add(self, ctx, user):
        # check that the user isn't the bot owner
        app_info = await self.bot.application_info()
        if getattr(self.bot, "owner_ids", None):
            owners = list(self.bot.owner_ids)
        else:
            owner = app_info.owner
            if isinstance(owner, Team):
                owners = [member.id for member in owner.members]
            else:
                owners = [owner.id]
        if user.id in owners:
            return await ctx.send(":x: You can't blacklist the bot owner.")

        # check that the user isn't already blacklisted
        no_user_mention = disnake.AllowedMentions(users=False)  # to avoid pinging user
        discord_db_user = await db_users.get_discord_user(user.id)
        if discord_db_user["is_blacklisted"]:
            return await ctx.send(
                ":x: <@{}> is already blacklisted.".format(user.id),
                allowed_mentions=no_user_mention,
            )

        # add to the blacklist
        await db_users.set_user_blacklist(user.id, True)
        return await ctx.send(
            ":white_check_mark: <@{}> has been blacklisted.".format(user.id),
            allowed_mentions=no_user_mention,
        )

    async def _do_blacklist_remove(self, ctx, user):
        # check that the user is actually blacklisted
        no_user_mention = disnake.AllowedMentions(users=False)  # to avoid pinging user
        discord_db_user = await db_users.get_discord_user(user.id)
        if not discord_db_user["is_blacklisted"]:
            return await ctx.send(
                ":x: <@{}> is not blacklisted.".format(user.id),
                allowed_mentions=no_user_mention,
            )

        # remove from the blacklist
        await db_users.set_user_blacklist(user.id, False)
        return await ctx.send(
            ":white_check_mark: <@{}> has been removed from the blacklist.".format(
                user.id
            ),
            allowed_mentions=no_user_mention,
        )

    async def _do_blacklist_list(self, ctx):
        blacklisted_users = await db_users.get_all_blacklisted_users()
        if blacklisted_users is None:
            return await ctx.send("**No users are blacklisted.**")
        else:
            text = "**Blacklisted users:**\n"
            for user_id in blacklisted_users:
                text += "\t• <@{}>\n".format(user_id)
            await ctx.send(text)

    async def _do_roleblacklist_add(self, ctx, role):
        await db_servers.update_blacklist_role(ctx.guild.id, role.id)
        await ctx.send(f":white_check_mark: Blacklist role set to <@&{role.id}>.")

    async def _do_roleblacklist_remove(self, ctx):
        await db_servers.update_blacklist_role(ctx.guild.id, None)
        await ctx.send(":white_check_mark: Blacklist role removed.")

    async def _do_roleblacklist_show(self, ctx):
        # show the current role
        current_role_id = await db_servers.get_blacklist_role(ctx.guild.id)
        if current_role_id is None:
            return await ctx.send(
                f"No blacklist role assigned, use `{get_display_prefix(self.bot)}{ctx.command} add <role>`"
            )
        current_role = ctx.guild.get_role(int(current_role_id))
        if current_role is None:
            return await ctx.send(
                f"The current blacklist role is invalid, use `{get_display_prefix(self.bot)}{ctx.command} <role>`"
            )
        else:
            return await ctx.send(f"Current blacklist role: <@&{current_role.id}>.")

    # --- prefix commands ---

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
            return await ctx.send(f":x: {e}")

        await self._do_blacklist_add(ctx, user)

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
            return await ctx.send(f":x: {e}")

        await self._do_blacklist_remove(ctx, user)

    @blacklist.command(description="Show all the blacklisted users.", aliases=["ls"])
    async def list(self, ctx):
        await self._do_blacklist_list(ctx)

    @commands.group(
        hidden=True,
        invoke_without_command=True,
        description="Show the current blacklist role.",
    )
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_roles=True))
    async def roleblacklist(self, ctx):
        await self._do_roleblacklist_show(ctx)

    @roleblacklist.command(
        description="Add a blacklist role, any user with this role won't be able to use the bot.",
        usage="<role name|role id|@role>",
    )
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_roles=True))
    async def add(self, ctx, role):
        # check that the role exists and save it
        try:
            role = await RoleConverter().convert(ctx, role)
        except RoleNotFound as e:
            return await ctx.send(f":x: {e}")
        await self._do_roleblacklist_add(ctx, role)

    @roleblacklist.command(description="Remove the current blacklist role.")
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_roles=True))
    async def remove(self, ctx):
        await self._do_roleblacklist_remove(ctx)

    # --- slash commands ---

    @commands.slash_command(
        name="blacklist",
        default_member_permissions=disnake.Permissions(administrator=True),
    )
    async def _blacklist(self, inter):
        pass

    @_blacklist.sub_command(name="add", description="Add a user to the blacklist.")
    @commands.is_owner()
    async def _blacklist_add(self, inter, user: disnake.User):
        await self._do_blacklist_add(inter, user)

    @_blacklist.sub_command(
        name="remove", description="Remove a user from the blacklist."
    )
    @commands.is_owner()
    async def _blacklist_remove(self, inter, user: disnake.User):
        await self._do_blacklist_remove(inter, user)

    @_blacklist.sub_command(name="list", description="Show all the blacklisted users.")
    @commands.is_owner()
    async def _blacklist_list(self, inter):
        await self._do_blacklist_list(inter)

    @commands.slash_command(
        name="roleblacklist",
        default_member_permissions=disnake.Permissions(manage_roles=True),
    )
    async def _roleblacklist(self, inter):
        pass

    @_roleblacklist.sub_command(
        name="add",
        description="Add a blacklist role, any user with this role won't be able to use the bot.",
    )
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_roles=True))
    async def _roleblacklist_add(self, inter, role: disnake.Role):
        await self._do_roleblacklist_add(inter, role)

    @_roleblacklist.sub_command(
        name="remove", description="Remove the current blacklist role."
    )
    @commands.check_any(commands.is_owner(), commands.has_permissions(manage_roles=True))
    async def _roleblacklist_remove(self, inter):
        await self._do_roleblacklist_remove(inter)


def setup(bot: commands.Bot):
    bot.add_cog(Blacklist(bot))
