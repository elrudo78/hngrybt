# cogs/database.py
# Handles database interactions using SQLite via aiosqlite.
# Incorporates:
# 1. Storing usernames alongside scores to avoid fetch-on-read.
# 2. Caching both username and score.

import discord # <<< CHANGE >>> Import discord for fetch_user and exceptions
from discord.ext import commands
import aiosqlite # Async SQLite driver
import logging
import asyncio
import os # To create directory if needed
import config

log = logging.getLogger(__name__)

# <<< CHANGE >>> Define a default name for cases where fetch fails
UNKNOWN_USERNAME = "Unknown User"

class UnscrambleDatabaseCog(commands.Cog, name="UnscrambleDB"):
    """Manages database operations using SQLite, storing usernames."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = config.UNSCRAMBLE_DB_FILENAME # Get path from config
        self.conn = None # Holds the connection object
        # <<< CHANGE >>> Cache now stores dicts: {user_id_str: {'name': str, 'score': int}}
        self.leaderboard_cache = {} # Renamed for clarity
        self.db_lock = asyncio.Lock() # Lock for critical write operations involving fetch

        # Ensure the directory for the database exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir)
                log.info(f"Created database directory: {db_dir}")
            except OSError as e:
                log.exception(f"Failed to create database directory {db_dir}: {e}")

        # Start DB initialization in the background
        self.init_task = self.bot.loop.create_task(self._initialize_database(), name="UnscrambleDBInit")
        log.info("Unscramble Database Cog initializing...")

    async def _initialize_database(self):
        """Connects to the SQLite DB and ensures the table exists. Loads cache."""
        try:
            log.info(f"Connecting to Unscramble SQLite database: {self.db_path}")
            self.conn = await aiosqlite.connect(self.db_path)
            log.info("Database connection established.")

            # Enable WAL mode immediately after connecting (best practice)
            await self.conn.execute("PRAGMA journal_mode=WAL;")
            log.info("SQLite journal mode set to WAL.")

            # <<< CHANGE >>> Create leaderboard table with username column
            await self.conn.execute("""
                CREATE TABLE IF NOT EXISTS leaderboard (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0
                )
            """)
            await self.conn.commit()
            log.info("Checked/Created 'leaderboard' table with user_id, username, score.")

            # Load initial data into the memory cache
            await self._load_cache()

        except aiosqlite.Error as e:
            log.exception(f"SQLite error during initialization: {e}")
            self.conn = None # Ensure connection is None if init failed
        except Exception as e:
            log.exception(f"Unexpected error during DB initialization: {e}")
            self.conn = None

        if not self.conn:
             log.critical("DATABASE CONNECTION FAILED. BOT MAY NOT FUNCTION CORRECTLY.")

    async def _load_cache(self):
        """Loads all scores and usernames from DB into the memory cache."""
        if not self.conn:
            log.error("Cannot load cache, no database connection.")
            return
        try:
            # <<< CHANGE >>> Select all three columns
            async with self.conn.execute("SELECT user_id, username, score FROM leaderboard") as cursor:
                rows = await cursor.fetchall()
            # <<< CHANGE >>> Populate cache with nested dictionaries
            self.leaderboard_cache = {
                str(user_id): {'name': str(username), 'score': int(score)}
                for user_id, username, score in rows
            }
            log.info(f"Loaded {len(self.leaderboard_cache)} user records into memory cache.")
        except aiosqlite.Error as e:
            log.exception(f"SQLite error loading cache: {e}")
        except Exception as e:
            log.exception(f"Unexpected error loading cache: {e}")

    # --- Public Accessor Methods ---
    async def get_leaderboard_data(self) -> dict:
        """Returns a copy of the current in-memory leaderboard cache."""
        if not self.conn and not self.init_task.done(): # Wait if init isn't finished
            try: await asyncio.wait_for(self.init_task, timeout=10.0)
            except asyncio.TimeoutError: log.error("DB Init task timed out waiting for get_leaderboard_data")
        return self.leaderboard_cache.copy() # Return the cache containing {'name': ..., 'score': ...}

    async def get_score(self, user_id: int) -> int:
        """Gets a user's current score from the in-memory cache."""
        if not self.conn and not self.init_task.done():
             try: await asyncio.wait_for(self.init_task, timeout=10.0)
             except asyncio.TimeoutError: log.error("DB Init task timed out waiting for get_score")

        user_id_str = str(user_id)
        # <<< CHANGE >>> Extract score from nested dict
        user_data = self.leaderboard_cache.get(user_id_str)
        return user_data['score'] if user_data else 0

    async def get_username(self, user_id: int) -> str:
        """Gets a user's cached username. Returns default if not found."""
        if not self.conn and not self.init_task.done():
            try: await asyncio.wait_for(self.init_task, timeout=10.0)
            except asyncio.TimeoutError: log.error("DB Init task timed out waiting for get_username")

        user_id_str = str(user_id)
        user_data = self.leaderboard_cache.get(user_id_str)
        return user_data['name'] if user_data else UNKNOWN_USERNAME


    # --- Update Methods (Writes to DB and updates cache) ---
    async def update_score(self, user_id: int, points_to_add: int) -> int:
        """Updates a user's score. Fetches & stores username on first win."""
        # <<< CHANGE >>> Major rewrite of this method
        if not self.conn: # If DB connection failed at startup
            log.error(f"Cannot update score for {user_id}, no DB connection.")
            # Fallback: Try to update score in cache only if user exists, otherwise return 0
            user_id_str = str(user_id)
            if user_id_str in self.leaderboard_cache:
                 self.leaderboard_cache[user_id_str]['score'] += points_to_add
                 return self.leaderboard_cache[user_id_str]['score']
            return 0

        user_id_str = str(user_id)
        new_score = 0

        # Use a lock to prevent potential race conditions if the *same user* triggers
        # this function twice very quickly before the first INSERT completes.
        async with self.db_lock:
            try:
                # 1. Try to update existing user's score
                cursor = await self.conn.execute(
                    "UPDATE leaderboard SET score = score + ? WHERE user_id = ?",
                    (points_to_add, user_id_str)
                )
                await self.conn.commit()

                # 2. Check if the update worked (user existed)
                if cursor.rowcount > 0:
                    log.debug(f"Updated score for existing user {user_id_str}.")
                    # Read the new score back (or calculate, but reading is safer)
                    async with self.conn.execute("SELECT score, username FROM leaderboard WHERE user_id = ?", (user_id_str,)) as read_cursor:
                        result = await read_cursor.fetchone()
                        if result:
                            new_score = result[0]
                            # Update cache
                            self.leaderboard_cache[user_id_str] = {'name': result[1], 'score': new_score}
                            log.debug(f"Cache updated for {user_id_str}: {self.leaderboard_cache[user_id_str]}")
                        else:
                             log.error(f"Failed to read back score for {user_id_str} after update!")
                             # Fallback: update cache based on calculation
                             current_score = self.leaderboard_cache.get(user_id_str, {}).get('score', 0)
                             new_score = current_score + points_to_add
                             current_name = self.leaderboard_cache.get(user_id_str, {}).get('name', UNKNOWN_USERNAME)
                             self.leaderboard_cache[user_id_str] = {'name': current_name, 'score': new_score}


                # 3. If update failed (rowcount is 0), user is new - Fetch name and Insert
                else:
                    log.info(f"User {user_id_str} not found. Attempting first-time insert.")
                    username = UNKNOWN_USERNAME # Default
                    try:
                        user = await self.bot.fetch_user(user_id)
                        # Prefer display_name for more context if available
                        username = user.name
                        log.info(f"Fetched username for {user_id_str}: {username}")
                    except discord.NotFound:
                        log.warning(f"Could not fetch Discord user {user_id_str}: User not found.")
                    except discord.HTTPException as e:
                         log.error(f"HTTP error fetching Discord user {user_id_str}: {e.status} {e.text}")
                    except Exception as e:
                        log.exception(f"Unexpected error fetching Discord user {user_id_str}: {e}")

                    # Calculate the initial score for the insert
                    initial_score = points_to_add # For a new user, points_to_add is their first score
                    new_score = initial_score

                    # Perform the INSERT
                    await self.conn.execute(
                        "INSERT INTO leaderboard (user_id, username, score) VALUES (?, ?, ?)",
                        (user_id_str, username, initial_score)
                    )
                    await self.conn.commit()
                    log.info(f"Inserted new user {user_id_str} ('{username}') with score {initial_score}.")

                    # Update cache for the new user
                    self.leaderboard_cache[user_id_str] = {'name': username, 'score': initial_score}

            except aiosqlite.Error as e:
                log.exception(f"SQLite error updating/inserting score for {user_id_str}: {e}")
                # Return score currently in cache as DB failed
                cached_data = self.leaderboard_cache.get(user_id_str)
                return cached_data['score'] if cached_data else 0
            except Exception as e:
                 log.exception(f"Unexpected error updating score for {user_id_str}: {e}")
                 cached_data = self.leaderboard_cache.get(user_id_str)
                 return cached_data['score'] if cached_data else 0

        return new_score # Return the final score determined


    async def reset_leaderboard(self):
        """Clears the leaderboard in the database and memory cache."""
        if not self.conn:
            log.error("Cannot reset leaderboard, no DB connection.")
            return False # Indicate failure

        log.warning("Reset leaderboard requested. Clearing data...")
        try:
            # <<< CHANGE >>> Ensure lock isn't held if something weird happens, though unlikely here
            async with self.db_lock:
                 await self.conn.execute("DELETE FROM leaderboard") # Delete all rows
                 await self.conn.commit()
                 self.leaderboard_cache = {} # Clear memory cache
            log.info("Leaderboard cleared successfully (DB & Cache).")
            return True # Indicate success
        except aiosqlite.Error as e:
            log.exception(f"SQLite error resetting leaderboard: {e}")
            return False
        except Exception as e:
            log.exception(f"Unexpected error resetting leaderboard: {e}")
            return False

    # --- Cog Lifecycle Methods ---
    async def cog_unload(self):
        """Closes the database connection gracefully on shutdown."""
        log.warning("Database Cog unloading. Closing connection...")
        # <<< CHANGE >>> Cancel init task if it's still running
        if hasattr(self, 'init_task') and not self.init_task.done():
             self.init_task.cancel()
             log.info("Cancelled pending DB initialization task.")

        if self.conn:
            try:
                await self.conn.close()
                log.info("Database connection closed.")
            except aiosqlite.Error as e:
                log.exception(f"Error closing SQLite connection: {e}")
            except Exception as e:
                log.exception(f"Unexpected error closing DB connection: {e}")
        else:
            log.info("No active database connection to close.")

# --- Setup Function ---
# <<< CHANGE >>> Update setup function name if needed (optional but good practice)
async def setup_unscramble_db(bot: commands.Bot):
    # Adds the *renamed* Cog to the bot
    await bot.add_cog(UnscrambleDatabaseCog(bot))
    log.info("Unscramble Database Cog added to bot.")

# Note: The setup function name doesn't *strictly* matter to discord.py's loader,
# which looks for a function named 'setup'. However, using distinct names can help
# avoid confusion if you ever inspect the loading process manually.
# If we keep it named 'setup', main.py's loader will just call it. Let's keep it 'setup' for simplicity with the loader.

async def setup(bot: commands.Bot): # <<< KEEP AS 'setup'
    await bot.add_cog(UnscrambleDatabaseCog(bot))
    log.info("Unscramble Database Cog added to bot.")
