# config.py
# Central configuration for the bot

import discord
import os # <<< CHANGE >>>

# --- Core Settings ---
COMMAND_PREFIX = "!"
DISCORD_TOKEN_ENV_VAR = "DISCORD_TOKEN" # Name of the secret in Codespaces/GitHub Secrets

# --- Role Settings ---
MOD_ROLE_NAME = "bot admin" # Role required for restricted commands

# --- Unscramble Game Settings ---
# <<< CHANGE >>> Define folder instead of file, and default behavior
WORDS_FOLDER = "data/wordlists"  # Folder containing .txt word lists
DEFAULT_THEME_NAME = "general"     # If no theme specified, use this (filename without .txt)
# Set DEFAULT_THEME_NAME to None to use a mix of all lists if no theme is chosen
UNSCRAMBLE_TIME_LIMIT_SECONDS = 60
STUCK_GAME_TIMEOUT_SECONDS = 300
UNSCRAMBLE_HINT_SCHEDULE_SECONDS = [20, 35, 45]

UNSCRAMBLE_LEADERBOARD_INTERVAL = 4 # Show leaderboard automatically every X rounds
UNSCRAMBLE_LEADERBOARD_EXTRA_DELAY = 4.0 # Extra seconds to wait after showing auto-leaderboard
UNSCRAMBLE_LEADERBOARD_ANTI_SPAM_SECONDS = 30 # Min seconds before showing end-game LB if auto-LB just shown

# --- Database Settings ---
UNSCRAMBLE_DB_FILENAME = "data/leaderboard.sqlite" # Filename for the SQLite database
# Ensure the data directory exists (can be done here or in database.py)
DATA_DIR = "data"
WORDLISTS_DIR = os.path.join(DATA_DIR, "wordlists") # Path to the wordlists folder
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
    print(f"Created directory: {DATA_DIR}")
if not os.path.exists(WORDLISTS_DIR):
    os.makedirs(WORDLISTS_DIR)
    print(f"Created directory: {WORDLISTS_DIR}")
    # <<< Optional: Create a default file if the folder was just created >>>
    # try:
    #     with open(os.path.join(WORDLISTS_DIR, f"{DEFAULT_THEME_NAME}.txt"), "w") as f:
    #         f.write("APPLE\nBANANA\nORANGE\n")
    #     print(f"Created default wordlist: {DEFAULT_THEME_NAME}.txt")
    # except Exception as e:
    #     print(f"Warning: Could not create default wordlist file: {e}")

# --- Embed Settings ---
EMBED_COLOR_DEFAULT = discord.Color.blue()
EMBED_COLOR_SUCCESS = discord.Color.green()
EMBED_COLOR_ERROR = discord.Color.red()
EMBED_COLOR_WARNING = discord.Color.orange()
EMBED_COLOR_INFO = discord.Color.gold()
EMBED_COLOR_HINT = discord.Color.blurple()

# --- Bot Activity ---
BOT_ACTIVITY_NAME = f"{COMMAND_PREFIX}help for commands" # <<< CHANGE >>> More generic activity
