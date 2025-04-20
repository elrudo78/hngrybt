# cogs/admin.py
# Contains administrative commands for the bot.

import discord
from discord.ext import commands
import logging
import config # Import shared configuration

log = logging.getLogger(__name__)

class UnscrambleAdminCog(commands.Cog, name="UnscrambleAdmin"):
    """Moderator/Admin level commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Getting cogs here is okay, but often better to get them inside commands
        # when needed to ensure they are loaded at runtime.
        # self.db_cog: DatabaseCog = self.bot.get_cog("Database")

    @commands.command(name='us_resetlb', aliases=['us_resetleaderboard'])
    @commands.has_role(config.MOD_ROLE_NAME) # Check for the moderator role
    @commands.guild_only() # Only in servers
    async def reset_leaderboard(self, ctx: commands.Context):
        """Resets the Unscramble leaderboard (requires role)."""
        log.warning(f"Unscramble Reset leaderboard command issued by {ctx.author} ({ctx.author.id}) in guild {ctx.guild.id}")

        db_cog = self.bot.get_cog("UnscrambleDB") # Get cog when needed
        if not db_cog:
             embed = discord.Embed(description="❌ Unscramble Database service is unavailable.", color=config.EMBED_COLOR_ERROR)
             await ctx.send(embed=embed)
             return

        try:
            success = await db_cog.reset_leaderboard() # Assumes reset_leaderboard returns True/False
            if success:
                 embed = discord.Embed(title="✅ Unscramble Leaderboard Reset!", description=f"Unscramble leaderboard cleared by {ctx.author.mention}.", color=config.EMBED_COLOR_SUCCESS)
            else:
                 embed = discord.Embed(title="⚠️ Unscramble Leaderboard Reset Issue", description="An error occurred during leaderboard reset. Check logs.", color=config.EMBED_COLOR_WARNING)
            await ctx.send(embed=embed)

        except Exception as e:
            log.exception(f"Error processing !us_resetlb command: {e}")
            embed = discord.Embed(description="❌ Oops! Error resetting Unscramble leaderboard.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)

    @commands.command(name='us_stop', aliases=['us_stopgame', 'us_cancelgame'])
    @commands.has_role(config.MOD_ROLE_NAME) # Role check
    @commands.guild_only()
    async def stop_game(self, ctx: commands.Context):
        """Force stops the active Unscramble game loop in this channel."""
        log.info(f"Unscramble Stop game loop requested by {ctx.author} in channel {ctx.channel.id}")
        channel_id = ctx.channel.id

        # <<< CHANGE >>> Central state check (using bot attribute directly for now)
        if not hasattr(self.bot, 'active_game_info') or not self.bot.active_game_info:
             embed = discord.Embed(description="🤔 No game seems to be active right now.", color=config.EMBED_COLOR_INFO)
             await ctx.send(embed=embed)
             return

        current_game_info = self.bot.active_game_info
        if current_game_info.get('game_type') != 'unscramble' or current_game_info.get('channel_id') != channel_id:
            embed = discord.Embed(description=f"🤔 An Unscramble game is not active in *this* channel (A {current_game_info.get('game_type', 'unknown')} game might be active elsewhere).", color=config.EMBED_COLOR_INFO)
            await ctx.send(embed=embed)
            return

        # Get the Unscramble Cog instance
        unscramble_cog = self.bot.get_cog("Unscramble")
        if not unscramble_cog:
            log.error("Unscramble Cog not found when trying to stop game loop.")
            embed = discord.Embed(description="❌ Internal error: Cannot access Unscramble game module.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)
            return

        # Check if loop exists and stop it using the active_loops dictionary
        if channel_id in unscramble_cog.active_loops:
            loop_data = unscramble_cog.active_loops.get(channel_id)
            main_loop_task = loop_data.get("loop_task") if loop_data else None

            log.warning(f"Stopping Unscramble game loop in channel {channel_id} by {ctx.author.name}.")

            if main_loop_task and not main_loop_task.done():
                # <<< CHANGE >>> Clear central state *before* cancelling
                log.info(f"Clearing active_game_info before stopping Unscramble game {channel_id}.")
                self.bot.active_game_info = {} # Clear the global state
                main_loop_task.cancel() # Cancel the main loop task
                # The loop's finally block handles removing from active_loops and final message
                # We send a confirmation here immediately
                embed = discord.Embed(description=f"🛑 Requesting stop for the ongoing Unscramble game...", color=config.EMBED_COLOR_WARNING)
                await ctx.send(embed=embed)
            else:
                # Task doesn't exist or already done, maybe cleanup failed? Remove manually.
                removed_data = unscramble_cog.active_loops.pop(channel_id, None)
                if removed_data:
                     log.warning(f"Unscramble loop task for {channel_id} not found/done during stop cmd, removed entry.")
                     self.bot.active_game_info = {} # Ensure state is cleared
                     # Remove from cog's internal dict too if possible
                     unscramble_cog.active_loops.pop(channel_id, None)
                     embed = discord.Embed(description=f"ℹ️ The Unscramble game was already stopping or stopped.", color=config.EMBED_COLOR_INFO)
                     await ctx.send(embed=embed)
                else:
                     # Loop not in cog's dict, means no loop was active. Ensure global state is clear just in case.
                     log.warning(f"Unscramble game loop not found in active_loops for {channel_id} during stop cmd, clearing global state.")
                     self.bot.active_game_info = {} # Ensure state is cleared
                     # Entry wasn't even in the dict, means no loop was active
                     embed = discord.Embed(description="🤔 No active Unscramble game found in this channel to stop.", color=config.EMBED_COLOR_INFO)
                     await ctx.send(embed=embed)

        else:
             # No loop active in this channel
             embed = discord.Embed(description="🤔 No Unscramble game seems to be active in this channel.", color=config.EMBED_COLOR_INFO)
             await ctx.send(embed=embed)


# Required setup function
async def setup(bot: commands.Bot):
    # No strict load-time dependencies needed here unless adding more complex commands
    await bot.add_cog(UnscrambleAdminCog(bot))
    log.info("Unscramble Admin Cog added to bot.")
