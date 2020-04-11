import typing
import collections
from datetime import datetime as dt, timedelta

import discord
from discord.ext import commands

from cogs import utils


class ModerationCommands(utils.Cog):

    def __init__(self, bot:utils.Bot):
        super().__init__(bot)
        self.watched_users = collections.defaultdict(list)  # (guildid, userid): [(modid, timestamp)]

    @utils.Cog.listener()
    async def on_guild_role_delete(self, role:discord.Role):
        """Remove roles from the server's settings when they're deleted from the guild"""

        if role.id in self.bot.guild_settings[role.guild].values():
            for i, o in self.bot.guild_settings[role.guild].items():
                if role.id == o:
                    self.bot.guild_settings[role.guild][i] = None
                    async with self.bot.database() as db:
                        await db(f"UPDATE guild_settings SET {i}=null WHERE guild_id=$1", role.guild.id)

    @commands.command(cls=utils.Command)
    @utils.checks.is_guild_moderator()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def mute(self, ctx:utils.Context, user:discord.Member, *, reason:str='<No reason provided>'):
        """Mutes a user from the server"""

        # Check if role exists
        muted_role_id = self.bot.guild_settings[ctx.guild.id].get("muted_role_id", None)
        if muted_role_id is None:
            return await ctx.send("There is no mute role set for this server.")

        # Check the user can run the command on who they want
        if user.top_role.position >= ctx.author.top_role.position:
            return await ctx.send("That user is too highly ranked for you to be able to punish them.")
        if user.top_role.position >= ctx.guild.me.top_role.position:
            return await ctx.send("That user is too highly ranked for me to be able to punish them.")

        # Grab the mute role
        mute_role = ctx.guild.get_role(muted_role_id)
        if mute_role is None:
            return await ctx.send("The mute role for this server is set to a deleted role.")
        if mute_role in user.roles:
            return await ctx.send(f"{user.mention} is already muted.")
        if mute_role.position >= ctx.guild.me.top_role.position:
            return await ctx.send("The mute role is too high for me to manage.")

        # DM the user
        dm_reason = f"You have been muted in **{ctx.guild.name}** with the reason `{reason}`."
        try:
            await user.send(dm_reason)
        except discord.Forbidden:
            pass  # Can't DM the user? Oh well

        # Mute the user
        manage_reason = f"{ctx.author!s}: {reason}"
        try:
            await user.add_roles(mute_role, reason=manage_reason)
        except discord.Forbidden:
            return await ctx.send(f"I was unable to add the mute role to {user.mention}.")
        except discord.NotFound:
            return await ctx.send("To me it looks like that user doesn't exist :/")

        # Throw the reason into the database
        self.bot.dispatch("moderation_action", moderator=ctx.author, user=user, reason=reason, action="Mute")

        # Output to chat
        return await ctx.send(f"{user.mention} has been muted by {ctx.author.mention} with reason `{reason}`.")

    @commands.command(cls=utils.Command)
    @utils.checks.is_guild_moderator()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def tempmute(self, ctx:utils.Context, user:discord.Member, duration:utils.TimeValue, *, reason:str='<No reason provided>'):
        """Mutes a user from the server"""

        # Check if role exists
        muted_role_id = self.bot.guild_settings[ctx.guild.id].get("muted_role_id", None)
        if muted_role_id is None:
            return await ctx.send("There is no mute role set for this server.")

        # Check the user can run the command on who they want
        if user.top_role.position >= ctx.author.top_role.position:
            return await ctx.send("That user is too highly ranked for you to be able to punish them.")
        if user.top_role.position >= ctx.guild.me.top_role.position:
            return await ctx.send("That user is too highly ranked for me to be able to punish them.")

        # Grab the mute role
        mute_role = ctx.guild.get_role(muted_role_id)
        if mute_role is None:
            return await ctx.send("The mute role for this server is set to a deleted role.")
        if mute_role in user.roles:
            return await ctx.send(f"{user.mention} is already muted.")
        if mute_role.position >= ctx.guild.me.top_role.position:
            return await ctx.send("The mute role is too high for me to manage.")

        # DM the user
        dm_reason = f"You have been temporarily muted in **{ctx.guild.name}** with the reason `{reason}`."
        try:
            await user.send(dm_reason)
        except discord.Forbidden:
            pass  # Can't DM the user? Oh well

        # Mute the user
        manage_reason = f"{ctx.author!s}: {reason}"
        try:
            await user.add_roles(mute_role, reason=manage_reason)
        except discord.Forbidden:
            return await ctx.send(f"I was unable to add the mute role to {user.mention}.")
        except discord.NotFound:
            return await ctx.send("To me it looks like that user doesn't exist :/")

        # Store the temporary role
        async with self.bot.database() as db:
            await db(
                """INSERT INTO temporary_roles (guild_id, role_id, user_id, remove_timestamp)
                VALUES ($1, $2, $3, $4)""",
                ctx.guild.id, muted_role_id, user.id, dt.utcnow() + duration.delta
            )

        # Throw the reason into the database
        self.bot.dispatch("moderation_action", moderator=ctx.author, user=user, reason=reason, action="Tempmute")

        # Output to chat
        return await ctx.send(f"{user.mention} has been muted for `{duration.clean_spaced}` by {ctx.author.mention} with reason `{reason}`.")

    @commands.command(cls=utils.Command)
    @utils.checks.is_guild_moderator()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def unmute(self, ctx:utils.Context, user:discord.Member, *, reason:str='<No reason provided>'):
        """Unmutes a user"""

        # Check if role exists
        muted_role_id = self.bot.guild_settings[ctx.guild.id].get("muted_role_id", None)
        if muted_role_id is None:
            return await ctx.send("There is no mute role set for this server.")

        # Check the user can run the command on who they want
        if user.top_role.position >= ctx.author.top_role.position:
            return await ctx.send("That user is too highly ranked for you to be able to punish them.")
        if user.top_role.position >= ctx.guild.me.top_role.position:
            return await ctx.send("That user is too highly ranked for me to be able to punish them.")

        # Grab the mute role
        mute_role = ctx.guild.get_role(muted_role_id)
        if mute_role is None:
            return await ctx.send("The mute role for this server is set to a deleted role.")
        if mute_role not in user.roles:
            return await ctx.send(f"{user.mention} is not muted.")
        if mute_role.position >= ctx.guild.me.top_role.position:
            return await ctx.send("The mute role is too high for me to manage.")

        # DM the user
        dm_reason = f"You have been unmuted in **{ctx.guild.name}** with the reason `{reason}`."
        try:
            await user.send(dm_reason)
        except discord.Forbidden:
            pass  # Can't DM the user? Oh well

        # Mute the user
        manage_reason = f"{ctx.author!s}: {reason}"
        try:
            await user.remove_roles(mute_role, reason=manage_reason)
        except discord.Forbidden:
            return await ctx.send(f"I was unable to remove the mute role from {user.mention}.")
        except discord.NotFound:
            return await ctx.send("To me it looks like that user doesn't exist :/")

        # Throw the reason into the database
        self.bot.dispatch("moderation_action", moderator=ctx.author, user=user, reason=reason, action="Unmute")

        # Remove role from db
        async with self.bot.database() as db:
            await db("DELETE FROM temporary_roles WHERE guild_id=$1 AND role_id=$2 AND user_id=$3", ctx.guild.id, muted_role_id, user.id)

        # Output to chat
        return await ctx.send(f"{user.mention} has been unmuted by {ctx.author.mention}.")

    @commands.command(cls=utils.Command)
    @utils.checks.is_guild_moderator()
    @commands.bot_has_permissions(send_messages=True)
    @commands.guild_only()
    async def warn(self, ctx:utils.Context, user:discord.Member, *, reason:str):
        """Adds a warning to a user"""

        # DM the user
        try:
            await user.send(f"You have been warned in **{ctx.guild.name}** with the reason `{reason}`.")
        except discord.Forbidden:
            pass

        # Throw the reason into the database
        self.bot.dispatch("moderation_action", moderator=ctx.author, user=user, reason=reason, action="Warn")

        # Warn the user
        return await ctx.send(f"{user.mention} has been warned by {ctx.author.mention} with reason `{reason}`.")

    @commands.command(cls=utils.Command)
    @utils.checks.is_guild_moderator()
    @commands.bot_has_permissions(send_messages=True)
    @commands.guild_only()
    async def watch(self, ctx:utils.Context, user:discord.Member, duration:utils.TimeValue=None):
        """Pipe all of a user's messages (in channels you can see) to your DMs for an hour"""

        if duration is None:
            delta = timedelta(hours=1)
        else:
            delta = duration.delta
        self.watched_users[(ctx.guild.id, user.id)].append((ctx.author.id, dt.utcnow() + delta))
        return await ctx.send("Now watching user.")

    @commands.command(cls=utils.Command)
    @utils.checks.is_guild_moderator()
    @commands.bot_has_permissions(send_messages=True)
    @commands.guild_only()
    async def unwatch(self, ctx:utils.Context, user:discord.Member):
        """Stop watching a user"""

        value = self.watched_users[(ctx.guild.id, user.id)]
        if value:
            self.watched_users[(ctx.guild.id, user.id)] = [i for i in value if i[0] != ctx.author.id]
            return await ctx.send("No longer watching user.")
        return await ctx.send("You aren't watching that user.")

    @utils.Cog.listener("on_message")
    async def user_watch_handler(self, message:discord.Message):
        """Handle pinging users"""

        # Get their watching mods
        if message.guild is None:
            return
        watching_mods = self.watched_users.get((message.guild.id, message.author.id))
        if watching_mods is None or len(watching_mods) == 0:
            return

        # DM the mod
        for mod_id, timestamp in watching_mods:
            if timestamp < dt.utcnow():
                continue
            moderator = message.guild.get_member(mod_id)
            if moderator is None:
                continue
            if message.channel.permissions_for(moderator).read_messages is False:
                continue
            try:
                await moderator.send(f"**Message from {message.author.mention} in {message.guild.name} ({message.channel.mention})**\n{message.content}")
            except (discord.Forbidden, discord.NotFound):
                pass

    @commands.command(cls=utils.Command)
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx:utils.Context, user:discord.Member, *, reason:str='<No reason provided>'):
        """Kicks a user from the server"""

        # Check the user can run the command on who they want
        if user.top_role.position >= ctx.author.top_role.position:
            return await ctx.send("That user is too highly ranked for you to be able to punish them.")
        if user.top_role.position >= ctx.guild.me.top_role.position:
            return await ctx.send("That user is too highly ranked for me to be able to punish them.")

        # DM the user
        dm_reason = f"You have been kicked from **{ctx.guild.name}** with the reason `{reason}`."
        try:
            await user.send(dm_reason)
        except discord.Forbidden:
            pass  # Can't DM the user? Oh well

        # Kick the user
        manage_reason = f"{ctx.author!s}: {reason}"
        try:
            await user.kick(reason=manage_reason)
        except discord.Forbidden:
            return await ctx.send(f"I was unable to kick {user.mention}.")
        except discord.NotFound:
            return await ctx.send("To me it looks like that user doesn't exist :/")

        # Throw the reason into the database
        self.bot.dispatch("moderation_action", moderator=ctx.author, user=user, reason=reason, action="Kick")

        # Output to chat
        return await ctx.send(f"{user.mention} has been kicked by {ctx.author.mention} with reason `{reason}`.")

    @commands.command(cls=utils.Command)
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx:utils.Context, user:typing.Union[discord.Member, int], *, reason:str='<No reason provided>'):
        """Bans a user from the server"""

        # Do some setup here for users not in the server
        if isinstance(user, int):
            user_in_guild = False
            user = discord.Object(user)
        else:
            user_in_guild = True

        # Check the user can run the command on who they want
        if user_in_guild and user.top_role.position >= user.top_role.position:
            return await ctx.send("That user is too highly ranked for you to be able to punish them.")
        if user_in_guild and user.top_role.position >= ctx.guild.me.top_role.position:
            return await ctx.send("That user is too highly ranked for me to be able to punish them.")

        # DM the user
        if user_in_guild:
            dm_reason = f"You have been kicked from **{ctx.guild.name}** with the reason `{reason}`."
            try:
                await user.send(dm_reason)
            except discord.Forbidden:
                pass  # Can't DM the user? Oh well

        # Kick the user
        manage_reason = f"{ctx.author!s}: {reason}"
        try:
            await ctx.guild.ban(user, reason=manage_reason)
        except discord.Forbidden:
            return await ctx.send(f"I was unable to ban {user.mention}.")
        except discord.NotFound:
            return await ctx.send("To me it looks like that user doesn't exist :/")

        # Throw the reason into the database
        self.bot.dispatch("moderation_action", moderator=ctx.author, user=user, reason=reason, action="Ban")

        # Output to chat
        await ctx.send(f"{user.mention} has been banned by {ctx.author.mention} with reason `{reason}`.")


def setup(bot:utils.Bot):
    x = ModerationCommands(bot)
    bot.add_cog(x)
