# main.py
# Main entry point for the Discord Bot (Codespaces Version)
# Updated for multi-game structure support

import discord
from discord.ext import commands
import os
import logging
import asyncio
import traceback
import config # Import our configuration file
import uvloop
import platform

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] [%(name)s]: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
main_log = logging.getLogger(__name__)

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True # Keep if needed for username fetching or other member operations

# <<< CHANGE >>> Initialize global game state tracker
bot = commands.Bot(command_prefix=config.COMMAND_PREFIX,
                   intents=intents,
                   case_insensitive=True,
                   help_command=None) # Keep custom help removed (will add global help cog later)
bot.active_game_info = {} # Initialize as empty dict to track the single active game

# --- Bot Events ---
@bot.event
async def on_ready():
    """Runs when the bot connects and is ready."""
    main_log.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    main_log.info(f'Command Prefix: {config.COMMAND_PREFIX}')
    main_log.info(f'Moderator Role: {config.MOD_ROLE_NAME}')
    main_log.info(f'discord.py version: {discord.__version__}')
    # <<< CHANGE >>> Log initial state of game tracker
    main_log.info(f'Initial active_game_info state: {bot.active_game_info}')

    # Set bot activity status (using the possibly updated generic name from config)
    activity = discord.Game(name=config.BOT_ACTIVITY_NAME)
    await bot.change_presence(status=discord.Status.online, activity=activity)
    main_log.info(f"Status: Online, Activity set to '{config.BOT_ACTIVITY_NAME}'.")
    main_log.info('------ Bot is Ready! ------')

# --- Optional Reload Command ---
# <<< CHANGE >>> Updated to take full extension path
@bot.command(name='reload', hidden=True)
@commands.is_owner()
async def _reload(ctx, extension_path: str): # e.g., cogs.game1_unscramble.unscramble_cog
    """Reloads a specific Cog using its full Python path."""
    # Example usage: !reload cogs.game1_unscramble.unscramble_cog
    main_log.warning(f"Reload command initiated by {ctx.author} for Extension: {extension_path}")
    try:
        await bot.reload_extension(extension_path) # Use the full path provided by the user
        await ctx.send(f"✅ Extension `{extension_path}` reloaded successfully.", delete_after=15)
        main_log.info(f"Extension '{extension_path}' reloaded.")
    except commands.ExtensionNotLoaded:
        await ctx.send(f"❌ Extension `{extension_path}` is not loaded. Cannot reload.", delete_after=15)
        main_log.warning(f"Reload failed: Extension '{extension_path}' not loaded.")
    except commands.ExtensionNotFound:
        await ctx.send(f"❌ Extension `{extension_path}` could not be found.", delete_after=15)
        main_log.error(f"Reload failed: Extension '{extension_path}' not found.")
    except commands.NoEntryPointError:
         await ctx.send(f"❌ Extension `{extension_path}` does not have a `setup` function.", delete_after=15)
         main_log.error(f"Reload failed: No setup function in '{extension_path}'.")
    except commands.ExtensionFailed as e:
         await ctx.send(f"❌ Extension `{extension_path}` failed during setup:\n```py\n{e.original}\n```")
         main_log.exception(f"Reload failed: Extension '{extension_path}' failed during setup.")
    except Exception as e:
        await ctx.send(f"❌ An unexpected error occurred while reloading `{extension_path}`:\n```py\n{e}\n```")
        main_log.exception(f"Unexpected error during reload of Extension: {extension_path}")

@_reload.error
async def reload_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("🚫 Please specify the full extension path to reload (e.g., `cogs.game1_unscramble.unscramble_cog`).", delete_after=15)
    elif isinstance(error, commands.NotOwner):
        await ctx.send("🚫 You do not have permission to use this command.", delete_after=10)
    else:
        main_log.error(f"Error executing reload command by {ctx.author}: {error}")
        await ctx.send("❌ An error occurred processing the reload command.", delete_after=10)


# --- Running the Bot ---
def run_bot():
    """Loads the token and runs the bot."""
    try:
        main_log.info("Attempting to load token from environment variable...")
        token = os.environ.get(config.DISCORD_TOKEN_ENV_VAR)
        if token is None:
             raise KeyError(config.DISCORD_TOKEN_ENV_VAR)
        if not isinstance(token, str) or not token:
             main_log.critical("Token invalid format.")
             raise ValueError("Invalid Token Format")

        # --- Run using async context manager ---
        async def runner():
             async def load_extensions():
                 main_log.info("Loading extensions following defined structure...")
                 loaded_extensions = []
                 failed_extensions = []

                 # <<< CHANGE >>> Define cog directories and explicit load order/paths
                 # Adjust paths based on your exact folder/file names
                 extensions_to_load = [
                     # Global Utilities First
                     "cogs.global_utils.error_handler",
                     # Game 1: Unscramble (Load DB first, then game logic, then commands)
                     "cogs.game1_unscramble.unscramble_db",
                     "cogs.game1_unscramble.unscramble_cog",
                     "cogs.game1_unscramble.unscramble_admin",
                     "cogs.game1_unscramble.unscramble_general",
                     # Game 2: Riddles (Example - Add later)
                     # "cogs.game2_riddles.riddles_db",
                     # "cogs.game2_riddles.riddles_cog",
                     # "cogs.game2_riddles.riddles_admin",
                     # "cogs.game2_riddles.riddles_general",
                     # Global Help Cog (Example - Add later)
                     # "cogs.global_utils.help_cog",
                 ]

                 for ext_path in extensions_to_load:
                     try:
                         await bot.load_extension(ext_path)
                         main_log.info(f"Successfully loaded: {ext_path}")
                         loaded_extensions.append(ext_path)
                     except commands.ExtensionAlreadyLoaded:
                         main_log.warning(f"Extension already loaded (skipped): {ext_path}")
                         if ext_path not in loaded_extensions: loaded_extensions.append(ext_path) # Still count as loaded
                     except commands.ExtensionNotFound:
                         main_log.error(f"Failed load: Extension not found at '{ext_path}'. Check path and filename.")
                         failed_extensions.append(ext_path)
                     except commands.NoEntryPointError:
                         main_log.error(f"Failed load: No `setup` function found in '{ext_path}'.")
                         failed_extensions.append(ext_path)
                     except commands.ExtensionFailed as e:
                         # Log the original exception raised during the extension's setup
                         main_log.exception(f"Failed load: Extension '{ext_path}' failed during its setup phase. Error: {e.original}")
                         failed_extensions.append(ext_path)
                     except Exception as e:
                         # Catch any other unexpected errors during loading
                         main_log.exception(f"Failed load: An unexpected error occurred loading '{ext_path}'.")
                         failed_extensions.append(ext_path)

                 main_log.info(f"Extension loading complete. Successfully loaded: {len(loaded_extensions)}, Failed: {len(failed_extensions)}")
                 if failed_extensions:
                     main_log.error(f"--- Failed Extensions ---")
                     for failed_ext in failed_extensions:
                         main_log.error(f" - {failed_ext}")
                     main_log.error(f"-------------------------")

                 # <<< CHANGE >>> Critical failure check
                 # Check if essential global cogs loaded (adjust class names if needed)
                 error_handler_cog = bot.get_cog("ErrorHandler") # Assuming class name is ErrorHandlerCog
                 if error_handler_cog is None:
                     main_log.critical("CRITICAL FAILURE: The global ErrorHandler Cog failed to load. Bot cannot start safely.")
                     return False # Indicate critical failure

                 # Game-specific critical dependencies (like DB) are checked within the game cogs' setup or __init__

                 return True # Indicate success or non-critical failures

             # <<< CHANGE >>> Inside runner, before starting bot
             bot.active_game_info = {} # Ensure state is reset cleanly on each run attempt

             async with bot:
                 if not await load_extensions(): # Check if critical cogs loaded
                     main_log.critical("Bot cannot start due to critical cog load failure.")
                     return # Don't start the bot

                 main_log.info("All essential extensions loaded. Starting bot connection...")
                 await bot.start(token, reconnect=True)

        # --- Run the runner ---
        try:
            # <<< CHANGE >>> Reset state before running
            if bot is not None: # Check if bot object exists
                 bot.active_game_info = {}
            asyncio.run(runner())
        except KeyboardInterrupt:
            main_log.warning("Shutdown requested via KeyboardInterrupt.")
        # <<< CHANGE >>> Catch specific discord errors during connection/runtime
        except discord.errors.LoginFailure:
            main_log.critical("FATAL: Login Failure - Please check your bot token.")
        except discord.errors.PrivilegedIntentsRequired:
            main_log.critical("FATAL: Privileged Intents (Members/Presence) are required but not enabled. Check Discord Developer Portal -> Bot -> Privileged Gateway Intents.")
        except Exception as e:
             # Catch other potential errors during asyncio.run or bot.start
             main_log.critical(f"UNEXPECTED ERROR DURING BOT RUNTIME: {type(e).__name__} - {e}")
             main_log.critical(traceback.format_exc())


    # --- Startup Environment Error Handling ---
    except KeyError:
        main_log.critical("-" * 50)
        main_log.critical(f"FATAL: Environment variable '{config.DISCORD_TOKEN_ENV_VAR}' not found!")
        main_log.critical("Ensure it is set correctly in your environment (e.g., GitHub Codespace secrets).")
        main_log.critical("-" * 50)
    except ValueError as e:
        main_log.critical(f"FATAL: Invalid Token Format - {e}")
    except Exception as e:
        # Catch unexpected errors during initial setup before asyncio.run
        main_log.critical(f"UNEXPECTED ERROR DURING INITIAL STARTUP: {type(e).__name__} - {e}")
        main_log.critical(traceback.format_exc())

# --- Script Entry Point ---
if __name__ == "__main__":
    # Install uvloop if possible (no changes needed here)
    try:
        main_log.info("Attempting to install uvloop...")
        uvloop.install()
        main_log.info("uvloop installed successfully and will be used.")
    except Exception as e:
        main_log.warning(f"Could not install uvloop, using default asyncio event loop: {e}")

    # Run the bot
    run_bot()
