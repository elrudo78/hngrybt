# cogs/unscramble.py
# Contains the logic and commands for the Unscramble game with auto-hints.
# VERSION FOR SINGLE WORDLIST FILE

import discord
from discord.ext import commands
import random
import time
import asyncio  # For sleep and task management
import logging
import config  # Import shared configuration
from .database import DatabaseCog  # Import the Database Cog

log = logging.getLogger(__name__)


class UnscrambleCog(commands.Cog, name="Unscramble"):
    """Commands and logic for the Unscramble game with automatic hints"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_games = {}  # { channel_id: game_data_dict }
        # --- Store words from the single file ---
        self.word_list = []
        # --- END ---
        self.db_cog: DatabaseCog = self.bot.get_cog("Database")

        if not self.db_cog:
            log.error(
                "!!! Database Cog not found. Unscramble game might not save scores correctly! !!!"
            )

        self._load_words()  # Call the single list loading function
        log.info("Unscramble Cog initialized.")

    # --- Word Loading (Single File Logic) ---
    def _load_words(self):
        """Loads words from the single configured file."""
        log.info(f"Loading words from '{config.WORDS_FILENAME}'...")
        try:
            # Use utf-8 encoding
            with open(config.WORDS_FILENAME, "r", encoding='utf-8') as f:
                self.word_list = [
                    line.strip().upper() for line in f if line.strip()
                ]
            if not self.word_list:
                log.warning(
                    f"Word file '{config.WORDS_FILENAME}' is empty. Using default."
                )
                self.word_list = ["DEFAULT"]
            log.info(
                f"Successfully loaded {len(self.word_list)} words from '{config.WORDS_FILENAME}'."
            )
        except FileNotFoundError:
            log.error(
                f"Word file '{config.WORDS_FILENAME}' not found! Using default word."
            )
            self.word_list = ["DEFAULT"]
        except Exception as e:
            log.exception(
                f"Failed to load words from '{config.WORDS_FILENAME}': {e}. Using default."
            )
            self.word_list = ["DEFAULT"]

    # --- Hint String Creation (Remains the same) ---
    def _create_hint_string(self, word, revealed_indices):
        """Creates the hint string with underscores for hidden letters."""
        hint_display = []
        for i, letter in enumerate(word):
            if i in revealed_indices:
                hint_display.append(f"**{letter}**")
            else:
                hint_display.append("＿")  # Fullwidth underscore
        return " ".join(hint_display)

    # --- Game Timeout Task (Remains the same) ---
    async def _game_timeout_task(self, channel: discord.TextChannel,
                                 channel_id: int, game_start_time: float,
                                 correct_word: str):
        """Background task to handle automatic game timeout."""
        try:
            await asyncio.sleep(config.TIME_LIMIT_SECONDS)
            current_game_data = self.active_games.get(channel_id)
            if current_game_data and current_game_data[
                    'start_time'] == game_start_time:
                log.info(
                    f"[Timeout Task] Game in channel {channel_id} timed out. Word was {correct_word}."
                )
                embed = discord.Embed(
                    title="⏱️ Time's Up!",
                    description=f"Aww, time ran out! Nobody guessed the word.\n"
                    f"The word was **{correct_word}**.\n\n"
                    f"Start a new game with `{config.COMMAND_PREFIX}unscramble`!",
                    color=config.EMBED_COLOR_ERROR)
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    log.exception(f"[Timeout Task] Error sending message: {e}")

                # Clean up - Also cancel hint task if it's still running
                if 'hint_task' in current_game_data and current_game_data[
                        'hint_task'] and not current_game_data[
                            'hint_task'].done():
                    current_game_data['hint_task'].cancel()
                del self.active_games[channel_id]
                log.info(
                    f"[Timeout Task] Game state for {channel_id} cleared due to timeout."
                )
            else:
                log.debug(
                    f"[Timeout Task] Game {channel_id} ended/changed. Task finished."
                )
        except asyncio.CancelledError:
            log.debug(f"[Timeout Task] {channel_id} cancelled.")
        except Exception as e:
            log.exception(f"[Timeout Task] Error {channel_id}: {e}")

    # --- Hint Scheduler Task (Remains the same logic, just added) ---
    async def _hint_scheduler_task(self, channel: discord.TextChannel,
                                   channel_id: int, game_start_time: float,
                                   correct_word: str, scrambled_word: str):
        """Runs in background, sleeping and sending scheduled hints."""
        last_hint_time = 0
        hints_shown_count = 0
        max_hints = max(0, len(correct_word) // 2)
        if len(correct_word) > 1 and max_hints == 0: max_hints = 1

        log.debug(
            f"[Hint Task {channel_id}] Starting. Max hints: {max_hints}. Schedule: {config.HINT_SCHEDULE_SECONDS}"
        )
        try:
            for scheduled_time in config.HINT_SCHEDULE_SECONDS:
                if hints_shown_count >= max_hints:
                    log.debug(f"[Hint Task {channel_id}] Max hints reached.")
                    break
                sleep_duration = scheduled_time - last_hint_time
                if sleep_duration <= 0: continue

                log.debug(
                    f"[Hint Task {channel_id}] Sleeping {sleep_duration}s until hint at {scheduled_time}s."
                )
                await asyncio.sleep(sleep_duration)
                last_hint_time = scheduled_time

                # CRITICAL Check: Is the *exact same* game still active?
                current_game_data = self.active_games.get(channel_id)
                if not current_game_data or current_game_data[
                        'start_time'] != game_start_time:
                    log.debug(
                        f"[Hint Task {channel_id}] Game ended/changed. Stopping."
                    )
                    break

                hints_shown_count += 1
                log.info(
                    f"[Hint Task {channel_id}] Triggering hint #{hints_shown_count} at {scheduled_time}s."
                )

                revealed_indices = current_game_data['revealed_indices']
                available_indices = [
                    i for i in range(len(correct_word))
                    if i not in revealed_indices
                ]
                if not available_indices:
                    log.warning(
                        f"[Hint Task {channel_id}] No indices for hint #{hints_shown_count}."
                    )
                    break

                index_to_reveal = random.choice(available_indices)
                revealed_indices.add(index_to_reveal)
                hint_display_string = self._create_hint_string(
                    correct_word, revealed_indices)
                current_game_data['hints_given'] = hints_shown_count

                embed = discord.Embed(
                    title=f"💡 Hint #{hints_shown_count}",
                    description=
                    (f"Stuck on **{scrambled_word}**?\n\n# {hint_display_string}"
                     ),
                    color=config.EMBED_COLOR_HINT)
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    log.exception(
                        f"[Hint Task {channel_id}] Failed send hint: {e}")

            log.debug(f"[Hint Task {channel_id}] Hint schedule finished.")
        except asyncio.CancelledError:
            log.debug(f"[Hint Task {channel_id}] cancelled.")
        except Exception as e:
            log.exception(f"[Hint Task {channel_id}] Error: {e}")

    # --- Game Command (Simplified for single wordlist) ---
    @commands.command(name='unscramble', aliases=['us'])
    @commands.has_role(config.MOD_ROLE_NAME)
    @commands.guild_only()
    async def unscramble(self,
                         ctx: commands.Context):  # Removed category argument
        """Starts a new Unscramble game."""  # Simplified docstring
        channel_id = ctx.channel.id

        # --- Check Word List ---
        if not self.word_list:  # Check if list loaded properly
            log.error("Word list is empty. Cannot start game.")
            embed = discord.Embed(
                description="❌ Error: The word list failed to load.",
                color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)
            return

        # --- Check for Existing/Stuck Game ---
        if channel_id in self.active_games:
            game_start_time = self.active_games[channel_id]['start_time']
            if time.time(
            ) - game_start_time > config.STUCK_GAME_TIMEOUT_SECONDS:
                log.warning(f"Clearing stuck game in channel {channel_id}.")
                embed = discord.Embed(
                    description=f"🧹 Previous game stuck. Starting new!",
                    color=config.EMBED_COLOR_WARNING)
                await ctx.send(embed=embed)
                old_game_data = self.active_games.get(channel_id)
                # Cancel tasks for stuck game
                if old_game_data:
                    if game_task := old_game_data.get(
                            'timeout_task'
                    ):  # Python 3.8+ assignment expression
                        if not game_task.done(): game_task.cancel()
                    if game_task := old_game_data.get('hint_task'):
                        if not game_task.done(): game_task.cancel()
                del self.active_games[channel_id]
            else:  # Game active
                embed = discord.Embed(
                    title="⏳ Game in Progress!",
                    description=
                    f"Guess: **{self.active_games[channel_id]['scrambled']}**",
                    color=config.EMBED_COLOR_WARNING)
                await ctx.send(embed=embed)
                return

        # --- Start New Game ---
        try:
            original_word = random.choice(
                self.word_list)  # Use the single list
            scrambled_word = original_word
            if len(original_word) > 1:
                word_letters = list(original_word)
                retry_count = 0
                while scrambled_word == original_word and retry_count < 5:
                    random.shuffle(word_letters)
                    scrambled_word = "".join(word_letters)
                    retry_count += 1

            current_time = time.time()
            game_data = {
                "word": original_word,
                "scrambled": scrambled_word,
                "start_time": current_time,
                "hints_given": 0,
                "revealed_indices": set(),
                "timeout_task": None,
                "hint_task": None
            }
            self.active_games[channel_id] = game_data

            # --- Send Start Message ---
            embed_desc = (
                f"Alright {ctx.author.mention}, unscramble this word:\n\n"  # Removed category mention
                f"# **{scrambled_word}**\n\n"
                f"You have **{config.TIME_LIMIT_SECONDS} seconds!** Type your answer.\n"
                f"Hints will appear automatically!")
            embed = discord.Embed(
                title="🧩 New Unscramble Challenge!",  # Simplified title
                description=embed_desc,
                color=config.EMBED_COLOR_DEFAULT)
            await ctx.send(embed=embed)
            log.info(
                f"Game started in {channel_id} by {ctx.author}. Word: '{original_word}'"
            )

            # --- Start Background Tasks ---
            game_data['timeout_task'] = asyncio.create_task(
                self._game_timeout_task(ctx.channel, channel_id, current_time,
                                        original_word),
                name=f"UnscrambleTimeout-{channel_id}")
            game_data['hint_task'] = asyncio.create_task(
                self._hint_scheduler_task(ctx.channel, channel_id,
                                          current_time, original_word,
                                          scrambled_word),
                name=f"HintScheduler-{channel_id}")
            log.debug(f"Timeout and Hint tasks created for {channel_id}")

        except Exception as e:
            log.exception(f"Error in !unscramble: {e}")
            embed = discord.Embed(description="❌ Oops! Error starting game.",
                                  color=config.EMBED_COLOR_ERROR)
            await ctx.send(embed=embed)
            if channel_id in self.active_games:  # Cleanup if partially created
                game = self.active_games.pop(channel_id)
                if task := game.get('timeout_task'):  # Python 3.8+
                    if not task.done(): task.cancel()
                if task := game.get('hint_task'):
                    if not task.done(): task.cancel()

        # --- Listener for Game Answers (First Winner Only Logic) ---
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for messages to check for game answers, processing only the first winner."""
        # --- Basic Filters ---
        if message.author == self.bot.user: return
        if not message.guild: return
        channel_id = message.channel.id

        # --- Quickly check if a game *might* be active ---
        # Use .get() for a quick, safe check before potentially heavier logic
        game_data_snapshot = self.active_games.get(channel_id)
        if not game_data_snapshot:
            return # No game active in this channel, exit fast

        # --- Ignore commands ---
        if message.content.startswith(config.COMMAND_PREFIX):
            return

        # --- Check Answer (using the snapshot) ---
        correct_word = game_data_snapshot.get("word")
        # Ensure word exists in snapshot before comparing
        if not correct_word or message.content.strip().upper() != correct_word:
            return # Not the correct answer, exit

        # --- Attempt to Claim Win (Atomic Deletion) ---
        # Now that we know it's the correct word, try to remove the game entry.
        # If we successfully remove it, we are the FIRST winner.
        try:
            # Use pop to atomically get and remove the game data if it still exists.
            # Pass None as default to avoid KeyError if already deleted by another process.
            game = self.active_games.pop(channel_id, None)

            if game is None:
                # The game was already removed (likely by another near-simultaneous winner).
                log.debug(f"User {message.author} answered correctly for game {channel_id}, but game already ended.")
                return # This user was too late

            # --- We are the FIRST winner! Process the win ---
            start_time = game["start_time"] # Get start time from the popped data
            time_taken = time.time() - start_time
            user_id = str(message.author.id)
            user_name = message.author.display_name
            log.info(f"FIRST WINNER! User: {user_name}({user_id}) in {channel_id}. Time: {time_taken:.2f}s")

            # --- Cancel Background Tasks (using popped game data) ---
            tasks_to_cancel = [game.get('timeout_task'), game.get('hint_task')]
            for task in tasks_to_cancel:
                 if task and not task.done():
                      try: task.cancel()
                      except Exception as e: log.error(f"Error cancelling task for winner {user_id}: {e}")

            # --- Calculate Points & Update Score (Single DB Write) ---
            points_earned = 0
            if time_taken <= config.TIME_LIMIT_SECONDS: # Check if within time limit
                # Adjust scoring tiers for 60 seconds as needed
                if time_taken <= 10: points_earned = 100
                elif time_taken <= 20: points_earned = 85
                elif time_taken <= 30: points_earned = 70
                elif time_taken <= 40: points_earned = 55
                elif time_taken <= 50: points_earned = 40
                else: points_earned = 25

                new_total_score = 0
                if self.db_cog:
                     new_total_score = await self.db_cog.update_score(message.author.id, points_earned)
                     log.info(f"Score updated for winner {user_id} to {new_total_score}.")
                else:
                     log.error(f"DB Cog missing, score not updated for winner {user_id}")

                # --- Send Win Message ---
                win_message = (f"You unscrambled **{correct_word}** in **{time_taken:.2f}**s!\nYou earned **{points_earned}** points.")
                win_embed = discord.Embed(title=f"🎉 Correct, {user_name}! 🎉", description=win_message, color=config.EMBED_COLOR_SUCCESS)
                if self.db_cog: win_embed.add_field(name="Your Total Score", value=f"**{new_total_score}** points")
                else: win_embed.set_footer(text="Score save error.")

                try:
                    await message.channel.send(embed=win_embed)
                except Exception as e:
                     log.exception(f"Failed to send win message for {user_id}: {e}")

            else: # Correct word, but time limit exceeded (Should technically be handled by timeout task first)
                # This block might be less likely to be hit if the timeout task is reliable,
                # but keep it as a fallback for answers arriving exactly as timeout occurs.
                log.info(f"User {user_name}({user_id}) answered correctly for {channel_id} BUT time was up ({time_taken:.2f}s).")
                embed = discord.Embed(title="⏰ Too Slow!", description=f"Yes, {user_name}, it was **{correct_word}**!\nBut time was already up ({time_taken:.2f}s > {config.TIME_LIMIT_SECONDS}s).\nNo points! 💨", color=config.EMBED_COLOR_WARNING)
                try:
                    await message.channel.send(embed=embed)
                except Exception as e:
                     log.exception(f"Failed to send 'too slow' message for {user_id}: {e}")

            # --- Game cleanup (task cancellation, del self.active_games) already done ---
            log.info(f"Game {channel_id} processing complete for winner {user_id}.")


        except Exception as e:
            # Catch any unexpected errors during the win processing itself
            log.exception(f"Unexpected error processing potential win in {channel_id} by {message.author}: {e}")
            # We might have popped the game state but failed before finishing.
            # State is already removed, so just log the error. Maybe inform admin?


# Required setup function for the cog
async def setup(bot: commands.Bot):
    db_cog = bot.get_cog("Database")
    if db_cog is None:
        log.critical("Database Cog required by Unscramble Cog is not loaded.")
        raise commands.ExtensionFailed("unscramble", "Database Cog not found.")
    await bot.add_cog(UnscrambleCog(bot))
    log.info("Unscramble Cog added to bot.")
