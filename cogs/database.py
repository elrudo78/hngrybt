# cogs/database.py
# Handles database interactions using SQLite via aiosqlite.

import discord
from discord.ext import commands
import aiosqlite # Async SQLite driver
import logging
import asyncio
import os # To create directory if needed
import config

log = logging.getLogger(__name__)

class DatabaseCog(commands.Cog, name="Database"):
    """Manages database operations using SQLite."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_path = config.SQLITE_DB_FILENAME # Get path from config
        self.conn = None # Holds the connection object
        self.leaderboard = {} # In-memory cache for fast reads

        # Ensure the directory for the database exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            try:
                os.makedirs(db_dir)
                log.info(f"Created database directory: {db_dir}")
            except OSError as e:
                log.exception(f"Failed to create database directory {db_dir}: {e}")
                # Depending on severity, you might want to raise an error here

        # Start DB initialization in the background
        self.init_task = self.bot.loop.create_task(self._initialize_database(), name="DBInit")
        log.info("Database Cog initializing...")

    async def _initialize_database(self):
        """Connects to the SQLite DB and ensures the table exists. Loads cache."""
        try:
            log.info(f"Connecting to SQLite database: {self.db_path}")
            # isolation_level=None enables autocommit mode for simpler writes if desired,
            # but manual commit gives more control. Let's use manual commit.
            self.conn = await aiosqlite.connect(self.db_path)
            log.info("Database connection established.")

            # Create leaderboard table if it doesn't exist
            await self.conn.execute("""
                CREATE TABLE IF NOT EXISTS leaderboard (
                    user_id TEXT PRIMARY KEY,
                    score INTEGER NOT NULL DEFAULT 0
                )
            """)
            await self.conn.commit()
            log.info("Checked/Created 'leaderboard' table.")

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
        """Loads all scores from DB into the memory cache."""
        if not self.conn:
            log.error("Cannot load cache, no database connection.")
            return
        try:
            async with self.conn.execute("SELECT user_id, score FROM leaderboard") as cursor:
                rows = await cursor.fetchall()
            self.leaderboard = {str(user_id): int(score) for user_id, score in rows}
            log.info(f"Loaded {len(self.leaderboard)} scores into memory cache.")
        except aiosqlite.Error as e:
            log.exception(f"SQLite error loading cache: {e}")
        except Exception as e:
            log.exception(f"Unexpected error loading cache: {e}")


    # --- Public Accessor Methods ---
    async def get_leaderboard_data(self) -> dict:
        """Returns a copy of the current in-memory leaderboard data."""
        if not self.conn and not self.init_task.done(): # Wait if init isn't finished
            await self.init_task
        return self.leaderboard.copy()

    async def get_score(self, user_id: int) -> int:
        """Gets a user's current score from the in-memory leaderboard."""
        if not self.conn and not self.init_task.done():
             await self.init_task
        return self.leaderboard.get(str(user_id), 0)

    # --- Update Methods (Writes to DB and updates cache) ---
    async def update_score(self, user_id: int, points_to_add: int) -> int:
        """Updates a user's score in DB and memory cache. Returns the new score."""
        if not self.conn: # If DB connection failed at startup
            log.error(f"Cannot update score for {user_id}, no DB connection.")
            # Optionally return current cached score or 0? Or raise error?
            return self.leaderboard.get(str(user_id), 0) # Return cached score as fallback

        user_id_str = str(user_id)
        # Get current score from cache for calculation
        current_score = self.leaderboard.get(user_id_str, 0)
        new_score = current_score + points_to_add

        try:
            # Use INSERT OR REPLACE (or INSERT...ON CONFLICT...UPDATE for newer SQLite)
            # This inserts if user_id doesn't exist, or replaces the row if it does.
            await self.conn.execute(
                "INSERT OR REPLACE INTO leaderboard (user_id, score) VALUES (?, ?)",
                (user_id_str, new_score)
            )
            await self.conn.commit() # Commit the change to the database file
            # Update cache ONLY after successful DB commit
            self.leaderboard[user_id_str] = new_score
            log.debug(f"Updated score for {user_id_str} to {new_score} (DB & Cache)")
            return new_score
        except aiosqlite.Error as e:
            log.exception(f"SQLite error updating score for {user_id_str}: {e}")
            # Return the score that's *currently* in the cache, as DB update failed
            return self.leaderboard.get(user_id_str, 0)
        except Exception as e:
             log.exception(f"Unexpected error updating score for {user_id_str}: {e}")
             return self.leaderboard.get(user_id_str, 0)

    async def reset_leaderboard(self):
        """Clears the leaderboard in the database and memory cache."""
        if not self.conn:
            log.error("Cannot reset leaderboard, no DB connection.")
            return False # Indicate failure

        log.warning("Reset leaderboard requested. Clearing data...")
        try:
            await self.conn.execute("DELETE FROM leaderboard") # Delete all rows
            await self.conn.commit()
            self.leaderboard = {} # Clear memory cache
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
async def setup(bot: commands.Bot):
    """Adds the Cog to the bot."""
    # No explicit dependency check needed here, but ensure it loads early in main.py
    await bot.add_cog(DatabaseCog(bot))
    log.info("Database Cog added to bot.")
