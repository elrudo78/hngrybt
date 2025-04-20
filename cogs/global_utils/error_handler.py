# cogs/error_handler.py
# Global error handling for commands.

import discord
from discord.ext import commands
import logging
import config # Import shared configuration
import sys
import traceback # For detailed logging

log = logging.getLogger(__name__)

class ErrorHandlerCog(commands.Cog, name="ErrorHandler"):
    """Handles errors globally."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log.info("ErrorHandler Cog initialized.")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """The event triggered when an error is raised while invoking a command."""

        # This prevents any commands with local handlers being handled here.
        if hasattr(ctx.command, 'on_error'):
            return

        # Allows us to check for original exceptions raised during command invocation.
        error = getattr(error, 'original', error)

        # --- User-Facing Errors (Missing Permissions, Bad Arguments) ---

        if isinstance(error, commands.CommandNotFound):
            # Optionally ignore this, or send a subtle message
            # log.info(f"Command not found: {ctx.message.content}")
            # await ctx.send(f"❓ Command not found. Try `{config.COMMAND_PREFIX}help`", delete_after=10)
            return # Often best to just ignore unknown commands silently

        if isinstance(error, commands.DisabledCommand):
            await ctx.send(f"🚫 Sorry, the command `{ctx.command}` has been disabled.", delete_after=10)
            log.warning(f"Disabled command {ctx.command} used by {ctx.author}.")
            return

        if isinstance(error, commands.UserInputError):
            # Base class for things like MissingRequiredArgument, BadArgument
            await ctx.send(f"⚠️ Invalid command input. Please check your arguments. Try `{config.COMMAND_PREFIX}help {ctx.command}` if available.", delete_after=15)
            log.warning(f"UserInputError for command {ctx.command} by {ctx.author}: {error}")
            return

        if isinstance(error, commands.NotOwner):
            await ctx.send("🚫 You do not have permission to use this owner-only command.", delete_after=10)
            log.warning(f"NotOwner error for command {ctx.command} by {ctx.author}.")
            return

        if isinstance(error, commands.MissingRole):
            # Error raised by @commands.has_role()
            await ctx.send(f"❌ You lack the required role ('{error.missing_role}') to use this command.", delete_after=15)
            log.warning(f"MissingRole error for command {ctx.command} by {ctx.author}. Missing: {error.missing_role}")
            return

        if isinstance(error, commands.MissingPermissions):
            # Error raised by @commands.has_permissions()
            missing_perms = ', '.join(error.missing_permissions).replace('_', ' ').title()
            await ctx.send(f"❌ You lack the required permissions to use this command: `{missing_perms}`.", delete_after=15)
            log.warning(f"MissingPermissions error for command {ctx.command} by {ctx.author}. Missing: {missing_perms}")
            return

        if isinstance(error, commands.CheckFailure):
            # Generic failure for other checks (like @commands.guild_only())
            await ctx.send("🚫 You do not meet the requirements to run this command here.", delete_after=10)
            log.warning(f"Generic CheckFailure for command {ctx.command} by {ctx.author}: {error}")
            return

        if isinstance(error, commands.CommandOnCooldown):
             await ctx.send(f"⏳ This command is on cooldown. Please try again in {error.retry_after:.2f} seconds.", delete_after=10)
             log.info(f"CommandOnCooldown for {ctx.command} by {ctx.author}.")
             return

        # --- Bot/Code Errors (Log these!) ---

        # For example, errors during API calls
        if isinstance(error, discord.HTTPException):
             await ctx.send(" interagindo com o Discord. Por favor, tente novamente mais tarde.", delete_after=10)
             log.error(f"Discord HTTPException during command {ctx.command}: {error.status} {error.code} {error.text}")
             return

        # If the error hasn't been handled yet, it's likely an unexpected internal error.
        log.error(f'Unhandled exception in command {ctx.command}:')
        # Log the full traceback
        log.error(''.join(traceback.format_exception(type(error), error, error.__traceback__)))

        # Send a generic error message to the user
        error_embed = discord.Embed(
            title="<:error:111111111111111111> Oops! Something Went Wrong", # Replace with actual emoji ID if desired
            description="An unexpected error occurred while processing your command. The developers have been notified.",
            color=config.EMBED_COLOR_ERROR
        )
        try:
            await ctx.send(embed=error_embed)
        except discord.HTTPException:
            log.error("Failed to send generic error message embed.")


# Required setup function
async def setup(bot: commands.Bot):
    await bot.add_cog(ErrorHandlerCog(bot))
    log.info("ErrorHandler Cog added to bot.")