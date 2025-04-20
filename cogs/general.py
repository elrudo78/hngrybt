# cogs/general.py
# Contains general purpose commands like help, leaderboard viewing.
# Integrates with DatabaseCog storing usernames.

import discord
from discord.ext import commands
import logging
import io         # <<< CHANGE >>> Added for file operations
import config     # Import shared configuration

log = logging.getLogger(__name__)

class UnscrambleGeneralCog(commands.Cog, name="UnscrambleGeneral"):
    """General commands specific to the Unscramble game (Leaderboard, etc)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # <<< CHANGE >>> Rename command and aliases
    @commands.command(name='us_lb', aliases=['us_leaderboard'])
    @commands.has_role(config.MOD_ROLE_NAME) # Role restricted
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        """Displays the top 10 Unscramble players."""
        log.info(f"Unscramble Leaderboard command issued by {ctx.author} in guild {ctx.guild.id}")

        # <<< CHANGE >>> Fetch specific Unscramble DB cog
        db_cog = self.bot.get_cog("UnscrambleDB")
        if not db_cog:
            embed = discord.Embed(description="❌ Unscramble Database service is unavailable. Cannot fetch leaderboard.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)
            return

        try:
            # <<< CHANGE >>> Fetch data using the new method
            leaderboard_data = await db_cog.get_leaderboard_data() # Gets {user_id: {'name': name, 'score': score}}

            if not leaderboard_data:
                embed = discord.Embed(description="📜 The leaderboard is currently empty! Play some rounds first.", color=config.EMBED_COLOR_INFO)
                await ctx.send(embed=embed)
                return

            # <<< CHANGE >>> Sort based on the nested score dictionary
            sorted_leaderboard = sorted(
                leaderboard_data.items(),
                key=lambda item: item[1].get('score', 0), # Safely get score
                reverse=True
            )

            embed = discord.Embed(title="🏆 Unscramble Leaderboard (Top 10) 🏆", color=config.EMBED_COLOR_INFO)
            lb_text = ""
            rank = 1
            entries_to_show = 10
            displayed_count = 0

            for user_id_key, user_data in sorted_leaderboard[:entries_to_show]:
                # <<< CHANGE >>> Use cached username and score directly
                user_display_name = user_data.get('name', f"Unknown ({user_id_key})")
                score = user_data.get('score', 0)

                # Only add users with a score > 0
                if score > 0:
                    lb_text += f"`{rank}.` {user_display_name}: **{score}** points\n"
                    rank += 1
                    displayed_count += 1

            if not lb_text: # Handle case where top 10 have 0 score or are empty after filtering
                lb_text = "No players with scores found in the top 10."

            embed.description = lb_text
            embed.set_footer(text=f"Showing top {displayed_count} players with scores.")
            await ctx.send(embed=embed)

        except Exception as e:
            log.exception(f"Error fetching or processing Unscramble leaderboard: {e}")
            embed = discord.Embed(description="❌ An error occurred while fetching the Unscramble leaderboard.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)


    # <<< CHANGE >>> New command added
    @commands.command(name='us_fulllb', aliases=['us_lball'])
    @commands.has_role(config.MOD_ROLE_NAME) # Role restricted
    @commands.guild_only()
    async def full_leaderboard(self, ctx: commands.Context):
        """Sends the complete Unscramble leaderboard (all players with scores) as a text file."""
        log.info(f"Unscramble Full Leaderboard file command issued by {ctx.author} in guild {ctx.guild.id}")

        # <<< CHANGE >>> Fetch specific Unscramble DB cog
        db_cog = self.bot.get_cog("UnscrambleDB")
        if not db_cog:
            embed = discord.Embed(description="❌ Database service is unavailable. Cannot fetch full leaderboard.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)
            return

        try:
            leaderboard_data = await db_cog.get_leaderboard_data() # Gets {user_id: {'name': name, 'score': score}}

            # Filter out users with 0 or None score explicitly, although DB should handle it.
            # Also converts to list for sorting: [(user_id, {'name': name, 'score': score}), ...]
            filtered_data = [
                item for item in leaderboard_data.items()
                if item[1].get('score', 0) > 0
            ]

            if not filtered_data:
                embed = discord.Embed(description="📜 The leaderboard is completely empty (no players with scores found).", color=config.EMBED_COLOR_INFO)
                await ctx.send(embed=embed)
                return

            # Sort leaderboard by score descending
            sorted_leaderboard = sorted(
                filtered_data,
                key=lambda item: item[1].get('score', 0),
                reverse=True
            )

            # Prepare the text content for the file
            lb_text_lines = [
                f"--- Full Unscramble Leaderboard ---",
                f"Server: {ctx.guild.name}",
                f"Generated: {discord.utils.format_dt(discord.utils.utcnow(), style='F')}", # Add timestamp
                f"Total Players with Score: {len(sorted_leaderboard)}",
                "------------------------------------",
                "" # Blank line
            ]
            rank = 1

            for user_id_key, user_data in sorted_leaderboard:
                # <<< CHANGE >>> Use cached username and score
                user_display_name = user_data.get('name', f"Unknown (ID: {user_id_key})") # Use cached name
                score = user_data.get('score', 0)

                lb_text_lines.append(f"{rank}. {user_display_name}: {score} points")
                rank += 1

            full_lb_text = "\n".join(lb_text_lines)

            # Create a file-like object in memory using io.BytesIO for UTF-8 encoding
            file_buffer = io.BytesIO(full_lb_text.encode('utf-8'))

            # Create a discord.File object
            discord_file = discord.File(fp=file_buffer, filename="full_unscramble_leaderboard.txt")

            # Send the file
            await ctx.send(f"📋 Here is the full Unscramble leaderboard ({len(sorted_leaderboard)} players):", file=discord_file)
            log.info(f"Sent full leaderboard file ({len(sorted_leaderboard)} entries) for guild {ctx.guild.id}")

        except Exception as e:
            log.exception(f"Error generating or sending Unscramble full leaderboard file: {e}")
            embed = discord.Embed(description="❌ An error occurred while generating the Unscramble full leaderboard file.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)


    # --- Placeholder for !rank command ---
    # @commands.command(name='rank')
    # @commands.guild_only()
    # async def rank_command(self, ctx: commands.Context, member: discord.Member = None):
    #     """Checks your Unscramble rank and score, or another member's."""
    #     target_user = member or ctx.author
    #     if not self.db_cog: ... # Handle DB error
    #
    #     user_id_str = str(target_user.id)
    #     user_data = (await self.db_cog.get_leaderboard_data()).get(user_id_str)
    #     score = user_data.get('score', 0) if user_data else 0
    #     name = user_data.get('name', target_user.display_name) if user_data else target_user.display_name
    #
    #     if score == 0:
    #         # Send embed saying user has no score
    #         ...
    #         return
    #
    #     # Fetch full data to calculate rank
    #     full_data = await self.db_cog.get_leaderboard_data()
    #     sorted_leaderboard = sorted(
    #            [item for item in full_data.items() if item[1].get('score', 0) > 0],
    #            key=lambda item: item[1].get('score', 0),
    #            reverse=True
    #        )
    #
    #     user_rank = -1
    #     for i, (uid, udata) in enumerate(sorted_leaderboard):
    #         if uid == user_id_str:
    #             user_rank = i + 1
    #             break
    #
    #     # Create and send embed with score and rank
    #     # embed = discord.Embed(...)
    #     # embed.description = f"**{name}**\nScore: **{score}**\nRank: **#{user_rank}**"
    #     # await ctx.send(embed=embed)


# Required setup function
async def setup(bot: commands.Bot): # <<< KEEP AS 'setup'
    # Need DB cog loaded before this, but main.py should handle load order.
    await bot.add_cog(UnscrambleGeneralCog(bot))
    log.info("Unscramble General Cog added to bot.")
