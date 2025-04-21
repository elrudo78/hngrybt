# cogs/global_utils/help_cog.py
# Implements an interactive, multi-step help command.

import discord
from discord.ext import commands
import logging
import asyncio # Needed for wait_for and TimeoutError
import config  # For COMMAND_PREFIX, MOD_ROLE_NAME

log = logging.getLogger(__name__)

class HelpCog(commands.Cog, name="Help"):
    """Provides an interactive help menu for different games."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log.info("Global Help Cog initialized.")

    # --- Helper to generate the Unscramble Specific Help Embed ---
    # This function replicates the exact structure you liked previously
    def _get_unscramble_help_embed(self) -> discord.Embed:
        """Generates the detailed help embed for the Unscramble game."""

        prefix = config.COMMAND_PREFIX

        embed = discord.Embed(title="🧩 Unscramble Bot Help 🧩",
                              description="Here are the commands you can use for Unscramble:",
                              color=config.EMBED_COLOR_DEFAULT)
        try:
            # Use bot's avatar for thumbnail
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        except Exception:
            pass # Ignore if avatar fetch fails

        # --- Moderator Commands Section ---
        mod_role_mention = f"Requires '{config.MOD_ROLE_NAME}' role."
        embed.add_field(name="--- Moderator Commands ---", value=mod_role_mention, inline=False)

        # Manually add each Unscramble command field
        embed.add_field(name=f"`{prefix}unscramble [rounds] [theme]` (or `us`)",
                        value="Starts Unscramble. Optional: specify `rounds`. Optional: specify `theme`. Uses default theme if omitted.", inline=False)

        # Attempt to add available themes dynamically
        try:
            unscramble_cog = self.bot.get_cog("Unscramble") # Cog name is "Unscramble"
            if unscramble_cog and hasattr(unscramble_cog, 'word_lists') and unscramble_cog.word_lists:
                 available_themes = list(unscramble_cog.word_lists.keys())
                 themes_str = ", ".join(f"`{t}`" for t in sorted(available_themes)) if available_themes else "None loaded"
                 embed.add_field(name="Available Themes", value=themes_str, inline=False)
            # Don't add field if themes cannot be loaded
        except Exception as e:
            log.warning(f"Could not fetch themes for help command: {e}")
            # Don't add the field if there's an error


        embed.add_field(name=f"`{prefix}us_lb` (or `us_leaderboard`)",
                        value="Shows the top 10 Unscramble players.", inline=False)
        embed.add_field(name=f"`{prefix}us_fulllb` (or `us_lball`)",
                        value="Sends a text file with the complete Unscramble leaderboard.", inline=False)
        embed.add_field(name=f"`{prefix}us_stop` (or `us_stopgame`, `us_cancelgame`)",
                        value="Force-stops the current Unscramble game in the channel.", inline=False)
        embed.add_field(name=f"`{prefix}us_resetlb` (or `us_resetleaderboard`)",
                        value="⚠️ Clears *all* Unscramble scores permanently.", inline=False)

        # --- General Commands Section ---
        # We only have the global help command itself here for now
        embed.add_field(name="--- General Commands ---", value="\u200b", inline=False) # Zero-width space for spacing
        embed.add_field(name=f"`{prefix}help` (or `h`, `commands`)",
                        value="Shows the initial game selection help menu.", inline=False) # Updated description


        embed.set_footer(text="Good luck and have fun unscrambling!")
        return embed

    # --- Helper to generate the (Future) Riddles Specific Help Embed ---
    def _get_riddles_help_embed(self) -> discord.Embed:
        """Generates the detailed help embed for the Riddles game."""
        prefix = config.COMMAND_PREFIX
        embed = discord.Embed(title="❓ Riddles Bot Help ❓",
                              description="Riddles game coming soon!", # Placeholder
                              color=config.EMBED_COLOR_INFO)
        # Add Riddle commands here later using embed.add_field(...)
        # e.g., !riddle, !riddle_lb, !riddle_stop, !riddle_resetlb
        embed.add_field(name=f"`{prefix}riddle [rounds] [theme]`", value="Starts the Riddles game (Coming Soon!).", inline=False)
        embed.set_footer(text="Prepare your brains!")
        return embed

    # --- Main Interactive Help Command ---
    @commands.command(name='help', aliases=['h', 'commands'])
    @commands.guild_only()
    async def help_command(self, ctx: commands.Context):
        """Shows an interactive help menu to select a game."""

        log.info(f"Interactive help started by {ctx.author} in guild {ctx.guild.id}.")

        # Define available games and map input number to the function that generates its help embed
        # IMPORTANT: Update this mapping when adding new games
        game_options = {
            "1": {
                "name": "Unscramble",
                "embed_func": self._get_unscramble_help_embed
            }
            # "2": {
            #     "name": "Riddles",
            #     "embed_func": self._get_riddles_help_embed
            # }
            # Add more games here
        }

        # Create the initial selection menu
        menu_description = "Please select the game you need help with by typing its number:\n\n"
        for number, game_data in game_options.items():
            menu_description += f"**{number}.** {game_data['name']}\n"
        menu_description += "\n*This request will time out in 30 seconds.*"

        menu_embed = discord.Embed(
            title="🎮 Game Help Selection 🎮",
            description=menu_description,
            color=config.EMBED_COLOR_DEFAULT
        )

        initial_message = await ctx.send(embed=menu_embed)

        # Define a check function for bot.wait_for
        def check(message: discord.Message) -> bool:
            # Check if the message is from the original author and in the same channel
            # Also check if the content is one of the valid game numbers
            return message.author == ctx.author and message.channel == ctx.channel and message.content in game_options

        try:
            # Wait for a valid response from the user
            response_message = await self.bot.wait_for('message', check=check, timeout=30.0) # 30 second timeout

            # User responded correctly, get the chosen option
            chosen_option = response_message.content
            selected_game_data = game_options[chosen_option]

            # Generate and send the specific help embed for the chosen game
            detailed_help_embed = selected_game_data["embed_func"]()
            await ctx.send(embed=detailed_help_embed)

            # Clean up messages
            try:
                await initial_message.delete() # Delete the selection prompt
                await response_message.delete() # Delete the user's number input
            except discord.HTTPException:
                pass # Ignore errors if messages were already deleted

        except asyncio.TimeoutError:
            # User didn't respond in time
            timeout_embed = discord.Embed(
                description="⏳ Help request timed out. Please type `!help` again if you need assistance.",
                color=config.EMBED_COLOR_WARNING
            )
            try:
                # Edit the initial message to show timeout instead of deleting
                await initial_message.edit(embed=timeout_embed, delete_after=15)
            except discord.HTTPException:
                pass # Ignore if initial message was deleted

        except Exception as e:
            log.exception(f"Error during interactive help session for {ctx.author}: {e}")
            await ctx.send("An unexpected error occurred during the help process.", delete_after=10)
            try:
               await initial_message.delete() # Clean up prompt on error too
            except discord.HTTPException:
               pass


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
    log.info("Global Help Cog added to bot.")
