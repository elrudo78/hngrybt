# main.py
# Main entry point for the Discord Bot (Codespaces Version)

import discord
from discord.ext import commands
import os
import logging
import asyncio
import traceback
import config # Import our configuration file
import uvloop
import platform
# No 'from replit import db' needed anymore

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
intents.members = True

bot = commands.Bot(command_prefix=config.COMMAND_PREFIX,
                   intents=intents,
                   case_insensitive=True,
                   help_command=None) # Use custom help

# --- Bot Events ---
@bot.event
async def on_ready():
    """Runs when the bot connects and is ready."""
    main_log.info(f'Logged in as {bot.user.name} ({bot.user.id})')
    main_log.info(f'Command Prefix: {config.COMMAND_PREFIX}')
    main_log.info(f'Moderator Role: {config.MOD_ROLE_NAME}')
    main_log.info(f'discord.py version: {discord.__version__}')

    # Set bot activity status
    activity = discord.Game(name=config.BOT_ACTIVITY_NAME)
    await bot.change_presence(status=discord.Status.online, activity=activity)
    main_log.info("Status: Online, Activity set.")
    main_log.info('------ Bot is Ready! ------')

# --- Optional Reload Command ---
@bot.command(name='reload', hidden=True)
@commands.is_owner()
async def _reload(ctx, cog_name: str):
    """Reloads a specific Cog."""
    main_log.warning(f"Reload command for Cog: {cog_name} by {ctx.author}")
    try:
        await bot.reload_extension(f"cogs.{cog_name}")
        await ctx.send(f"✅ Cog '{cog_name}' reloaded.", delete_after=10)
        main_log.info(f"Cog '{cog_name}' reloaded.")
    except commands.ExtensionNotLoaded: await ctx.send(f"❌ Cog '{cog_name}' not loaded.", delete_after=10)
    except commands.ExtensionNotFound: await ctx.send(f"❌ Cog 'cogs.{cog_name}' not found.", delete_after=10)
    except Exception as e:
        await ctx.send(f"❌ Failed reload '{cog_name}':\n```py\n{e}\n```")
        main_log.exception(f"Failed reload Cog: {cog_name}")

@_reload.error
async def reload_error(ctx, error):
    if isinstance(error, commands.NotOwner): await ctx.send("🚫 Not owner.", delete_after=10)
    else: main_log.error(f"Error in reload cmd: {error}")

# --- Running the Bot ---
def run_bot():
    """Loads the token and runs the bot."""
    try:
        main_log.info("Attempting to load token from environment variable...")
        # Get token purely from environment variable set in Codespaces Secrets
        token = os.environ.get(config.DISCORD_TOKEN_ENV_VAR)
        if token is None:
             # No fallback needed or desired outside Replit
             raise KeyError(config.DISCORD_TOKEN_ENV_VAR)

        if not isinstance(token, str) or not token:
             main_log.critical("Token invalid format.")
             raise ValueError("Invalid Token Format")

        # --- Run using async context manager ---
        async def runner():
             async def load_extensions():
                 main_log.info("Loading extensions...")
                 loaded_cogs = []
                 failed_cogs = []
                 initial_cogs = ['database', 'error_handler'] # Load DB & Error Handler first
                 for cog_name in initial_cogs:
                      try:
                          await bot.load_extension(f'cogs.{cog_name}')
                          main_log.info(f"Loaded initial: {cog_name}")
                          loaded_cogs.append(cog_name)
                      except Exception as e:
                          main_log.exception(f"Failed initial load: {cog_name}")
                          failed_cogs.append(cog_name)
                          if cog_name == 'database': # Critical failure if DB fails
                               main_log.critical("Database cog failed to load. Aborting.")
                               return False # Indicate failure
                 # Load remaining
                 for filename in os.listdir('./cogs'):
                      if filename.endswith('.py') and filename[:-3] not in loaded_cogs and filename[:-3] not in failed_cogs and filename != '__init__.py':
                           cog_name = filename[:-3]
                           try:
                               await bot.load_extension(f'cogs.{cog_name}')
                               main_log.info(f"Loaded: {cog_name}")
                               loaded_cogs.append(cog_name)
                           except Exception as e:
                                main_log.exception(f"Failed load: {cog_name}")
                                failed_cogs.append(cog_name)
                 main_log.info(f"Cog loading done. Loaded: {len(loaded_cogs)}, Failed: {len(failed_cogs)}")
                 if failed_cogs: main_log.error(f"Failed Cogs: {', '.join(failed_cogs)}")
                 return True # Indicate success

             async with bot:
                 if not await load_extensions(): # Check if critical cogs loaded
                     main_log.critical("Bot cannot start due to critical cog load failure.")
                     return # Don't start the bot

                 main_log.info("Starting bot connection...")
                 await bot.start(token, reconnect=True)

        try:
            asyncio.run(runner())
        except KeyboardInterrupt:
            main_log.warning("Shutdown requested via KeyboardInterrupt.")

    # --- Startup Error Handling ---
    except KeyError:
        main_log.critical("-" * 50)
        main_log.critical(f"FATAL: {config.DISCORD_TOKEN_ENV_VAR} not found in Environment Variables!")
        main_log.critical("Ensure it is set in your GitHub Codespace secrets.")
        main_log.critical("-" * 50)
    except ValueError as e: main_log.critical(f"FATAL: Invalid Token - {e}")
    except discord.errors.LoginFailure: main_log.critical("FATAL: Login Failure - Check token.")
    except discord.errors.PrivilegedIntentsRequired: main_log.critical("FATAL: Check Discord Developer Portal -> Bot -> Privileged Gateway Intents.")
    except Exception as e:
        main_log.critical(f"UNEXPECTED ERROR ON STARTUP/RUNTIME: {type(e).__name__} - {e}")
        main_log.critical(traceback.format_exc())

# --- Script Entry Point ---
if __name__ == "__main__":
    # Install uvloop automatically replaces the default asyncio event loop policy
    # It's generally recommended to do this early, before the loop starts.
    # Only install on Linux/macOS typically, but harmless on Windows (won't be used)
    # if platform.system() != "Windows": # Optional check if you might run on Windows
    try:
        main_log.info("Attempting to install uvloop...")
        uvloop.install()
        main_log.info("uvloop installed successfully.")
    except Exception as e:
        main_log.warning(f"Could not install uvloop, using default asyncio loop: {e}")

    # Now run the bot as before
    run_bot()
