# cogs/general.py
# Contains general purpose commands like help, leaderboard viewing.
# Integrates with DatabaseCog storing usernames.

import discord
from discord.ext import commands
import logging
import io         # <<< CHANGE >>> Added for file operations
import config     # Import shared configuration
from .database import DatabaseCog # Import the Database Cog

log = logging.getLogger(__name__)

class GeneralCog(commands.Cog, name="General"):
    """General informational and utility commands"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # <<< CHANGE >>> Get Database Cog instance robustly
        # It's better to potentially get it inside commands if load order is uncertain,
        # but since it's checked at setup, getting it here is okay.
        # If DatabaseCog fails to load, this cog's setup will fail.
        self.db_cog: DatabaseCog = self.bot.get_cog("Database")
        if not self.db_cog:
            # This log might not even be reached if setup fails first, but good practice.
            log.critical("!!! General Cog initialized BUT Database Cog is missing! Commands will fail. !!!")

    @commands.command(name='leaderboard', aliases=['lb'])
    @commands.has_role(config.MOD_ROLE_NAME) # Role restricted
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context):
        """Displays the top 10 Unscramble players."""
        log.info(f"Leaderboard command issued by {ctx.author} in guild {ctx.guild.id}")

        if not self.db_cog:
            embed = discord.Embed(description="❌ Database service is unavailable. Cannot fetch leaderboard.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)
            return

        try:
            # <<< CHANGE >>> Fetch data using the new method
            leaderboard_data = await self.db_cog.get_leaderboard_data() # Gets {user_id: {'name': name, 'score': score}}

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
            log.exception(f"Error fetching or processing leaderboard: {e}")
            embed = discord.Embed(description="❌ An error occurred while fetching the leaderboard.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)


    # <<< CHANGE >>> New command added
    @commands.command(name='fulllb', aliases=['lball'])
    @commands.has_role(config.MOD_ROLE_NAME) # Role restricted
    @commands.guild_only()
    async def full_leaderboard(self, ctx: commands.Context):
        """Sends the complete leaderboard (all players with scores) as a text file."""
        log.info(f"Full Leaderboard file command issued by {ctx.author} in guild {ctx.guild.id}")

        if not self.db_cog:
            embed = discord.Embed(description="❌ Database service is unavailable. Cannot fetch full leaderboard.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)
            return

        try:
            leaderboard_data = await self.db_cog.get_leaderboard_data() # Gets {user_id: {'name': name, 'score': score}}

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
            await ctx.send(f"📋 Here is the full leaderboard ({len(sorted_leaderboard)} players):", file=discord_file)
            log.info(f"Sent full leaderboard file ({len(sorted_leaderboard)} entries) for guild {ctx.guild.id}")

        except Exception as e:
            log.exception(f"Error generating or sending full leaderboard file: {e}")
            embed = discord.Embed(description="❌ An error occurred while generating the full leaderboard file.", color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)


    # <<< CHANGE >>> Help command updated for new features/roles
    @commands.command(name='help', aliases=['h', 'commands'])
    # @commands.has_role(config.MOD_ROLE_NAME) # Decide if help is restricted or open
    @commands.guild_only() # Keep in guilds
    async def help_command(self, ctx: commands.Context):
        """Shows this help message listing available commands."""
        log.info(f"Help command requested by {ctx.author} in guild {ctx.guild.id}")

        embed = discord.Embed(title="🧩 Unscramble Bot Help 🧩",
                              description="Here are the commands you can use:",
                              color=config.EMBED_COLOR_DEFAULT)
        try: embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        except Exception: pass # Ignore if avatar fetch fails

        # --- Moderator Commands ---
        mod_role_mention = f"Requires '{config.MOD_ROLE_NAME}' role."
        embed.add_field(name="--- Moderator Commands ---", value=mod_role_mention, inline=False)

        # <<< CHANGE >>> Updated description for !unscramble
        embed.add_field(name=f"`{config.COMMAND_PREFIX}unscramble [rounds] [theme]` (or `us`)",
                        value="Starts Unscramble. Optional: specify `rounds`. Optional: specify `theme` (e.g., `foods`). Uses default theme if omitted.", inline=False)

        # <<< CHANGE >>> Add a way to list themes (could be its own command too)
        try:
            unscramble_cog = self.bot.get_cog("Unscramble")
            if unscramble_cog and unscramble_cog.word_lists:
                 available_themes = list(unscramble_cog.word_lists.keys())
                 themes_str = ", ".join(f"`{t}`" for t in sorted(available_themes)) if available_themes else "None loaded"
                 embed.add_field(name="Available Themes", value=themes_str, inline=False)
            else:
                 embed.add_field(name="Available Themes", value="Could not load themes.", inline=False)
        except Exception as e:
            log.warning(f"Could not fetch themes for help command: {e}")
            embed.add_field(name="Available Themes", value="Error fetching themes.", inline=False)

        
        embed.add_field(name=f"`{config.COMMAND_PREFIX}leaderboard` (or `lb`)",
                        value="Shows the top 10 players.", inline=False)
        embed.add_field(name=f"`{config.COMMAND_PREFIX}fulllb` (or `lball`)",
                        value="Sends a text file with the complete leaderboard.", inline=False)
        embed.add_field(name=f"`{config.COMMAND_PREFIX}stop` (or `stopgame`, `cancelgame`)",
                        value="Force-stops the current Unscramble game in the channel.", inline=False)
        embed.add_field(name=f"`{config.COMMAND_PREFIX}resetleaderboard` (or `resetlb`)",
                        value="⚠️ Clears *all* Unscramble scores permanently.", inline=False)

        # --- General Commands ---
        # If help isn't restricted, list public commands here
        embed.add_field(name="--- General Commands ---", value="\u200b", inline=False) # Zero-width space for spacing
        embed.add_field(name=f"`{config.COMMAND_PREFIX}help` (or `h`, `commands`)",
                        value="Shows this help message.", inline=False)
        # Add !rank command here when implemented

        embed.set_footer(text="Good luck and have fun unscrambling!")
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
async def setup(bot: commands.Bot):
    # <<< CHANGE >>> Explicit dependency check for Database Cog
    db_cog = bot.get_cog("Database")
    if db_cog is None:
        log.critical("FATAL: Database Cog is required by General Cog but was not found/loaded.")
        raise commands.ExtensionFailed("general", "Setup failed: Database Cog not found.")
    else:
        await bot.add_cog(GeneralCog(bot))
        log.info("General Cog added to bot.")
