# config.py
# Central configuration for the bot

import discord

# --- Core Settings ---
COMMAND_PREFIX = "!"
DISCORD_TOKEN_ENV_VAR = "DISCORD_TOKEN" # Name of the secret in Codespaces/GitHub Secrets

# --- Role Settings ---
MOD_ROLE_NAME = "bot admin" # Role required for restricted commands

# --- Unscramble Game Settings ---
WORDS_FILENAME = "words.txt" # Assumes single word list file
TIME_LIMIT_SECONDS = 60
STUCK_GAME_TIMEOUT_SECONDS = 300
HINT_SCHEDULE_SECONDS = [20, 35, 45]

LEADERBOARD_INTERVAL = 3 # Show leaderboard automatically every X rounds
LEADERBOARD_EXTRA_DELAY = 3.0 # Extra seconds to wait before showing auto-leaderboard
LEADERBOARD_ANTI_SPAM_SECONDS = 120 # Min seconds before showing end-game LB if auto-LB just shown

# --- Database Settings ---
SQLITE_DB_FILENAME = "data/leaderboard.sqlite" # Filename for the SQLite database
# LEADERBOARD_DB_KEY = "unscramble_leaderboard" # <-- REMOVED

# --- Embed Settings ---
EMBED_COLOR_DEFAULT = discord.Color.blue()
EMBED_COLOR_SUCCESS = discord.Color.green()
EMBED_COLOR_ERROR = discord.Color.red()
EMBED_COLOR_WARNING = discord.Color.orange()
EMBED_COLOR_INFO = discord.Color.gold()
EMBED_COLOR_HINT = discord.Color.blurple()

# --- Bot Activity ---
BOT_ACTIVITY_NAME = f"{COMMAND_PREFIX}unscramble"
