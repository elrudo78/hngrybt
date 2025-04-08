# cogs/admin.py
# Contains administrative commands for the bot.

import discord
from discord.ext import commands
import logging
import config # Import shared configuration
from .database import DatabaseCog # To reset leaderboard

log = logging.getLogger(__name__)

class AdminCog(commands.Cog, name="Admin"):
    """Moderator/Admin level commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Getting cogs here is okay, but often better to get them inside commands
        # when needed to ensure they are loaded at runtime.
        # self.db_cog: DatabaseCog = self.bot.get_cog("Database")

    @commands.command(name='resetleaderboard', aliases=['resetlb'])
    @commands.has_role(config.MOD_ROLE_NAME) # Check for the moderator role
    @commands.guild_only() # Only in servers
    async def reset_leaderboard(self, ctx: commands.Context):
        """Resets the Unscramble leaderboard (requires role)."""
        log.warning(f"Reset leaderboard command issued by {ctx.author} ({ctx.author.id}) in guild {ctx.guild.id}")

        db_cog = self.bot.get_cog("Database") # Get cog when needed
        if not db_cog:
             embed = discord.Embed(description="❌ Database service is unavailable.", color=config.EMBED_COLOR_ERROR)
             await ctx.send(embed=embed)
             return

        try:
            success = await db_cog.reset_leaderboard() # Assumes reset_leaderboard returns True/False
            if success:
                 embed = discord.Embed(title="✅ Leaderboard Reset!", description=f"Leaderboard cleared by {ctx.author.mention}.", color=config.EMBED_COLOR_SUCCESS)
            else:
                 embed = discord.Embed(title="⚠️ Leaderboard Reset Issue", description="An error occurred during leaderboard reset. Check logs.", color=config.EMBED_COLOR_WARNING)
            await ctx.send(embed=embed)

        except Exception as e:
            log.exception(f"Error processing !resetleaderboard command: {e}")
            embed = discord.Embed(description="❌ Oops! Error resetting leaderboard.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)

    @commands.command(name='stop', aliases=['stopgame', 'cancelgame'])
    @commands.has_role(config.MOD_ROLE_NAME) # Role check
    @commands.guild_only()
    async def stop_game(self, ctx: commands.Context):
        """Force stops the active Unscramble game loop in this channel."""
        log.info(f"Stop game loop requested by {ctx.author} in channel {ctx.channel.id}")
        channel_id = ctx.channel.id

        # Get the Unscramble Cog instance
        unscramble_cog = self.bot.get_cog("Unscramble")
        if not unscramble_cog:
            log.error("Unscramble Cog not found when trying to stop game loop.")
            embed = discord.Embed(description="❌ Internal error: Cannot access game module.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)
            return

        # Check if loop exists and stop it using the active_loops dictionary
        if channel_id in unscramble_cog.active_loops:
            loop_data = unscramble_cog.active_loops.get(channel_id)
            main_loop_task = loop_data.get("loop_task") if loop_data else None

            log.warning(f"Stopping game loop in channel {channel_id} by {ctx.author.name}.")

            if main_loop_task and not main_loop_task.done():
                main_loop_task.cancel() # Cancel the main loop task
                # The loop's finally block handles removing from active_loops and final message
                # We send a confirmation here immediately
                embed = discord.Embed(description=f"🛑 Requesting stop for the ongoing Unscramble game...", color=config.EMBED_COLOR_WARNING)
                await ctx.send(embed=embed)
            else:
                # Task doesn't exist or already done, maybe cleanup failed? Remove manually.
                removed_data = unscramble_cog.active_loops.pop(channel_id, None)
                if removed_data:
                     log.warning(f"Loop task for {channel_id} not found/done during stop cmd, removed entry.")
                     embed = discord.Embed(description=f"ℹ️ The game was already stopping or stopped.", color=config.EMBED_COLOR_INFO)
                     await ctx.send(embed=embed)
                else:
                    # Entry wasn't even in the dict, means no loop was active
                     embed = discord.Embed(description="🤔 No active game found in this channel to stop.", color=config.EMBED_COLOR_INFO)
                     await ctx.send(embed=embed)

        else:
             # No loop active in this channel
             embed = discord.Embed(description="🤔 No Unscramble game seems to be active in this channel.", color=config.EMBED_COLOR_INFO)
             await ctx.send(embed=embed)


# Required setup function
async def setup(bot: commands.Bot):
    # No strict load-time dependencies needed here unless adding more complex commands
    await bot.add_cog(AdminCog(bot))
    log.info("Admin Cog added to bot.")
