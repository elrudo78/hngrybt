# cogs/unscramble.py
# Game logic for auto-running Unscramble loop with auto-hints.

import discord
from discord.ext import commands
import random
import time
import asyncio
import logging
import config
from .database import DatabaseCog

log = logging.getLogger(__name__)

class UnscrambleCog(commands.Cog, name="Unscramble"):
    """Auto-running Unscramble game loop with automatic hints"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # --- State for active game loops per channel ---
        self.active_loops = {}
        # --- Load single word list ---
        self.word_list = []
        self.db_cog: DatabaseCog = self.bot.get_cog("Database")

        if not self.db_cog: log.error("!!! Database Cog not found! Scores may not save. !!!")
        self._load_words()
        log.info("Unscramble Cog initialized.")

    def _load_words(self):
        """Loads words from the single configured file."""
        log.info(f"Loading words from '{config.WORDS_FILENAME}'...")
        try:
            with open(config.WORDS_FILENAME, "r", encoding='utf-8') as f:
                self.word_list = [line.strip().upper() for line in f if line.strip()]
            if not self.word_list:
                log.warning(f"Word file '{config.WORDS_FILENAME}' is empty. Using default.")
                self.word_list = ["DEFAULT"]
            log.info(f"Loaded {len(self.word_list)} words from '{config.WORDS_FILENAME}'.")
        except FileNotFoundError:
            log.error(f"Word file '{config.WORDS_FILENAME}' not found! Using default.")
            self.word_list = ["DEFAULT"]
        except Exception as e:
            log.exception(f"Failed loading words from '{config.WORDS_FILENAME}': {e}")
            self.word_list = ["DEFAULT"]

    def _create_hint_string(self, word, revealed_indices):
        """Creates the hint string like W O R _"""
        hint_display = []
        for i, letter in enumerate(word):
            if i in revealed_indices: hint_display.append(f"**{letter}**")
            else: hint_display.append("＿") # Fullwidth underscore U+FF3F
        return " ".join(hint_display)

    async def _game_timeout_task(self, channel: discord.TextChannel, channel_id: int, round_start_time: float, correct_word: str, loop_data: dict):
        """Background task for per-round timeout. Updates loop state."""
        try:
            await asyncio.sleep(config.TIME_LIMIT_SECONDS)

            active_loop_data = self.active_loops.get(channel_id)
            if not active_loop_data: return

            # Use pop to safely get details for the specific round this task belongs to
            current_round_details = active_loop_data.get("current_round_details")
            if not current_round_details or current_round_details['start_time'] != round_start_time:
                log.debug(f"[Timeout Task {channel_id}] Round ended or changed before timeout.")
                return

            # --- Process Timeout ---
            current_r = active_loop_data['current_round']
            log.info(f"[Timeout Task {channel_id}] Round {current_r} timed out. Word: {correct_word}.")

            active_loop_data["consecutive_timeouts"] += 1
            active_loop_data["round_status"] = "TIMEOUT"

            timeout_embed = discord.Embed(
                title=f"⏱️ Time's Up! (Round {current_r})",
                description=f"Nobody guessed the word!\nThe word was **{correct_word}**.",
                color=config.EMBED_COLOR_ERROR
            )

            # --- Attempt Embed Recycling ---
            edited_message = False
            last_msg_id = active_loop_data.get("last_round_message_id")
            if last_msg_id:
                try:
                    msg_to_edit = await channel.fetch_message(last_msg_id)
                    await msg_to_edit.edit(content=None, embed=timeout_embed, view=None)
                    active_loop_data["last_round_message_id"] = msg_to_edit.id # Keep same ID
                    edited_message = True
                except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                    log.warning(f"[Timeout Task {channel_id}] Failed edit message {last_msg_id}: {e}. Sending new.")

            if not edited_message: # Send new if edit failed or no previous ID
                 try:
                      sent_msg = await channel.send(embed=timeout_embed)
                      active_loop_data["last_round_message_id"] = sent_msg.id # Store new ID
                 except Exception as e:
                      log.exception(f"[Timeout Task {channel_id}] Failed sending new timeout message: {e}")

            # Cancel this round's hint task (if it exists in details and is running)
            hint_task = current_round_details.get("hint_task_ref")
            if hint_task and not hint_task.done(): hint_task.cancel()

            # Signal the main loop
            active_loop_data["round_complete_event"].set()

        except asyncio.CancelledError: log.debug(f"[Timeout Task {channel_id}] Cancelled.")
        except Exception as e: log.exception(f"[Timeout Task {channel_id}] Error: {e}")

    async def _hint_scheduler_task(self, channel: discord.TextChannel, channel_id: int, round_start_time: float, correct_word: str, scrambled_word: str, loop_data: dict):
        """Runs in background, sending hints for the current round."""
        last_hint_time = 0
        hints_shown_count = 0
        max_hints = max(0, len(correct_word) // 2);
        if len(correct_word) > 1 and max_hints == 0: max_hints = 1

        current_r = loop_data.get("current_round", "?")
        log.debug(f"[Hint Task {channel_id}-{current_r}] Starting. Max: {max_hints}. Schedule: {config.HINT_SCHEDULE_SECONDS}")
        try:
            for scheduled_time in config.HINT_SCHEDULE_SECONDS:
                # Check against current hints_given in shared state, in case it changed
                active_loop_data = self.active_loops.get(channel_id)
                if not active_loop_data: break # Loop ended
                current_round_details = active_loop_data.get("current_round_details")
                if not current_round_details or current_round_details['start_time'] != round_start_time: break # Round changed
                if current_round_details['hints_given'] >= max_hints: break # Max hints reached

                sleep_duration = scheduled_time - last_hint_time
                if sleep_duration <= 0: continue

                await asyncio.sleep(sleep_duration)
                last_hint_time = scheduled_time

                # Re-check game state *after* sleep
                active_loop_data = self.active_loops.get(channel_id)
                if not active_loop_data: break
                current_round_details = active_loop_data.get("current_round_details")
                if not current_round_details or current_round_details['start_time'] != round_start_time: break
                if current_round_details['hints_given'] >= max_hints: break

                hints_shown_count = current_round_details['hints_given'] + 1 # Increment based on shared state
                log.info(f"[Hint Task {channel_id}-{current_r}] Triggering hint #{hints_shown_count} @ {scheduled_time}s.")

                revealed_indices = current_round_details['revealed_indices']
                available_indices = [i for i in range(len(correct_word)) if i not in revealed_indices]
                if not available_indices: break

                index_to_reveal = random.choice(available_indices)
                revealed_indices.add(index_to_reveal) # Update shared set
                current_round_details['hints_given'] = hints_shown_count # Update shared counter

                hint_display_string = self._create_hint_string(correct_word, revealed_indices)
                embed = discord.Embed(title=f"💡 Hint #{hints_shown_count}", description=f"Stuck on **{scrambled_word}**?\n\n# {hint_display_string}", color=config.EMBED_COLOR_HINT)
                try: await channel.send(embed=embed) # Send hints as new messages
                except Exception as e: log.exception(f"[Hint Task {channel_id}-{current_r}] Failed send hint: {e}")

            log.debug(f"[Hint Task {channel_id}-{current_r}] Hint schedule finished.")
        except asyncio.CancelledError: log.debug(f"[Hint Task {channel_id}-{current_r}] Cancelled.")
        except Exception as e: log.exception(f"[Hint Task {channel_id}-{current_r}] Error: {e}")

    @commands.command(name='unscramble', aliases=['us'])
    @commands.has_role(config.MOD_ROLE_NAME)
    @commands.guild_only()
    async def unscramble(self, ctx: commands.Context, rounds: str = None):
        """Starts an auto-running Unscramble loop [num_rounds]. Runs infinitely if no number given."""
        channel_id = ctx.channel.id

        if channel_id in self.active_loops:
            await ctx.send(embed=discord.Embed(title="⏳ Loop Already Running", description="Game loop already active.", color=config.EMBED_COLOR_WARNING))
            return

        target_rounds = float('inf'); is_infinite = True
        if rounds is not None:
            try:
                num_rounds = int(rounds); assert num_rounds > 0
                target_rounds = num_rounds; is_infinite = False
            except (ValueError, AssertionError):
                await ctx.send(f"Invalid rounds: `{rounds}`. Use positive number or leave blank.")
                return

        if not self.word_list:
             await ctx.send(embed=discord.Embed(description="❌ Error: Word list not loaded.", color=config.EMBED_COLOR_ERROR))
             return

        loop_data = {
            "loop_task": None, "target_rounds": target_rounds, "current_round": 0,
            "consecutive_timeouts": 0, "round_complete_event": asyncio.Event(),
            "last_round_message_id": None, "round_status": None,
            "channel_id": channel_id, "guild_id": ctx.guild.id
        }

        log.info(f"Starting game loop: Ch {channel_id}, Rounds {'inf' if is_infinite else target_rounds}, By {ctx.author}")
        game_loop_task = self.bot.loop.create_task(
            self._channel_game_loop(ctx, loop_data), name=f"GameLoop-{channel_id}"
        )
        loop_data["loop_task"] = game_loop_task
        self.active_loops[channel_id] = loop_data

        start_msg = f"✅ Unscramble auto-game started for **{'infinite' if is_infinite else target_rounds}** rounds!"
        await ctx.send(embed=discord.Embed(description=start_msg, color=config.EMBED_COLOR_SUCCESS))

    async def _channel_game_loop(self, ctx: commands.Context, loop_data: dict):
        """Main async task managing the auto-running game loop for a channel."""
        channel_id = loop_data["channel_id"]
        round_delay = 3.0
        round_timeout_task = None # Define here for finally block
        round_hint_task = None

        try:
            while True:
                loop_data["current_round"] += 1
                current_r = loop_data["current_round"]
                target_r = loop_data["target_rounds"]
                timeouts = loop_data["consecutive_timeouts"]
                log.info(f"[Loop {channel_id}] Starting Round {current_r} (Target: {target_r}, Timeouts: {timeouts})")

                if current_r > target_r:
                    log.info(f"[Loop {channel_id}] Target rounds reached.")
                    await ctx.send(embed=discord.Embed(description=f"🏁 Game finished after {int(target_r)} rounds!", color=config.EMBED_COLOR_INFO))
                    break

                if timeouts >= 2:
                    log.warning(f"[Loop {channel_id}] Stopping loop: {timeouts} consecutive timeouts.")
                    await ctx.send(embed=discord.Embed(description=f"😴 Stopping game: {timeouts} rounds timed out.", color=config.EMBED_COLOR_WARNING))
                    break

                loop_data["round_complete_event"].clear()
                loop_data["round_status"] = None
                round_timeout_task = None # Reset task vars for this round
                round_hint_task = None

                # --- Run One Round ---
                try:
                    original_word = random.choice(self.word_list)
                    scrambled_word = original_word
                    if len(original_word) > 1:
                        word_letters=list(original_word); random.shuffle(word_letters); scrambled_word="".join(word_letters)

                    current_round_details = {
                         "word": original_word, "start_time": time.time(),
                         "revealed_indices": set(), "hints_given": 0,
                         "loop_data_ref": loop_data, # Important reference back
                         "timeout_task_ref": None, "hint_task_ref": None
                    }
                    loop_data["current_round_details"] = current_round_details # Attach to loop

                    round_title = f"🧩 Round {current_r}" + (f"/{int(target_r)}" if target_r != float('inf') else "")
                    round_desc = f"Unscramble this word:\n\n# **{scrambled_word}**\n\n*Time: {config.TIME_LIMIT_SECONDS}s. Auto-hints.*"
                    round_embed = discord.Embed(title=round_title, description=round_desc, color=config.EMBED_COLOR_DEFAULT)
                    if target_r != float('inf'): round_embed.set_footer(text=f"Progress: {current_r}/{int(target_r)}")

                    # --- Embed Recycling Attempt ---
                    sent_message = None
                    last_msg_id = loop_data.get("last_round_message_id")
                    next_round_toast = discord.Embed(description="⏭️ Next round starting...", color=config.EMBED_COLOR_INFO)
                    if last_msg_id:
                        try:
                            msg_to_edit = await ctx.channel.fetch_message(last_msg_id)
                            await msg_to_edit.edit(content=None, embed=next_round_toast, view=None)
                            await asyncio.sleep(1.5)
                            await msg_to_edit.edit(embed=round_embed)
                            sent_message = msg_to_edit
                        except Exception as e:
                            log.warning(f"[Loop {channel_id}] Edit fail {last_msg_id}: {e}. Sending new.")
                            sent_message = await ctx.send(embed=round_embed)
                    else: sent_message = await ctx.send(embed=round_embed)
                    if sent_message: loop_data["last_round_message_id"] = sent_message.id
                    # --- End Embed Recycling ---

                    # --- Start Per-Round Tasks & Store Refs ---
                    current_start_time = current_round_details["start_time"]
                    round_timeout_task = self.bot.loop.create_task(
                        self._game_timeout_task(ctx.channel, channel_id, current_start_time, original_word, loop_data),
                        name=f"Timeout-{channel_id}-{current_r}" )
                    current_round_details["timeout_task_ref"] = round_timeout_task

                    round_hint_task = self.bot.loop.create_task(
                        self._hint_scheduler_task(ctx.channel, channel_id, current_start_time, original_word, scrambled_word, loop_data),
                        name=f"Hints-{channel_id}-{current_r}" )
                    current_round_details["hint_task_ref"] = round_hint_task
                    log.debug(f"[Loop {channel_id}] Per-round tasks created for round {current_r}")

                    # --- Wait for Win/Timeout ---
                    await loop_data["round_complete_event"].wait()
                    log.debug(f"[Loop {channel_id}] Round {current_r} complete event. Status: {loop_data.get('round_status')}")

                except Exception as round_e:
                    log.exception(f"[Loop {channel_id}] Error in round {current_r}: {round_e}")
                    await ctx.send(embed=discord.Embed(title="⚠️ Round Error", description="Trying next round...", color=config.EMBED_COLOR_ERROR))
                    # Fall through to finally block for cleanup

                finally:
                    # --- Per-Round Cleanup ---
                    # Ensure tasks for this specific round are cancelled
                    if round_timeout_task and not round_timeout_task.done(): round_timeout_task.cancel()
                    if round_hint_task and not round_hint_task.done(): round_hint_task.cancel()
                    loop_data.pop("current_round_details", None) # Remove temporary round data

                # --- Post-Round Delay ---
                await asyncio.sleep(round_delay)
                # Loop continues...

        except asyncio.CancelledError:
            log.info(f"[Loop {channel_id}] Game loop task cancelled.")
            await ctx.send(embed=discord.Embed(description="🛑 Game loop stopped.", color=config.EMBED_COLOR_WARNING))
        except Exception as loop_e:
            log.exception(f"[Loop {channel_id}] CRITICAL error in game loop: {loop_e}")
            await ctx.send(embed=discord.Embed(title="💥 Loop Error", description="Game loop stopped unexpectedly.", color=config.EMBED_COLOR_ERROR))
        finally:
            log.info(f"[Loop {channel_id}] Cleaning up loop state.")
            self.active_loops.pop(channel_id, None) # Remove from active loops dict

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for answers and processes the first winner for an active loop."""
        if message.author == self.bot.user or not message.guild: return
        channel_id = message.channel.id

        active_loop_data = self.active_loops.get(channel_id)
        if not active_loop_data: return

        current_round_details = active_loop_data.get("current_round_details")
        if not current_round_details: return # Round transitioning

        if message.content.startswith(config.COMMAND_PREFIX): return

        correct_word = current_round_details.get("word")
        if not correct_word or message.content.strip().upper() != correct_word: return

        # --- Correct Answer Received ---
        # Check if round already completed using the event
        if not active_loop_data["round_complete_event"].is_set():
            # --- We are the FIRST winner for this round ---
            start_time = current_round_details["start_time"]
            time_taken = time.time() - start_time
            user_id = str(message.author.id)
            user_name = message.author.display_name
            current_r = active_loop_data["current_round"]
            log.info(f"WINNER! User: {user_name}({user_id}) in {channel_id} round {current_r}. Time: {time_taken:.2f}s")

            # Signal completion FIRST
            active_loop_data["round_status"] = "WIN"
            active_loop_data["round_complete_event"].set()

            # Cancel this round's tasks
            tasks_to_cancel = [current_round_details.get('timeout_task_ref'), current_round_details.get('hint_task_ref')]
            for task in tasks_to_cancel:
                 if task and not task.done():
                      try: task.cancel()
                      except Exception as e: log.error(f"Error cancelling task on win r{current_r}: {e}")

            # Reset consecutive timeouts counter
            active_loop_data["consecutive_timeouts"] = 0

            # --- Calculate Points & Update Score ---
            points_earned = 0
            if time_taken <= config.TIME_LIMIT_SECONDS:
                # Adjust scoring tiers for 60s
                if time_taken <= 10: points_earned = 100
                elif time_taken <= 20: points_earned = 85
                elif time_taken <= 30: points_earned = 70
                elif time_taken <= 40: points_earned = 55
                elif time_taken <= 50: points_earned = 40
                else: points_earned = 25

                new_total_score = 0
                if self.db_cog: new_total_score = await self.db_cog.update_score(message.author.id, points_earned)
                else: log.error(f"DB Cog missing, score not updated winner {user_id}")

                # --- Send Win Message (Attempt Edit) ---
                win_message = f"You unscrambled **{correct_word}** in **{time_taken:.2f}**s!\nYou earned **{points_earned}** points."
                win_embed = discord.Embed(title=f"🎉 Correct, {user_name}! (Round {current_r}) 🎉", description=win_message, color=config.EMBED_COLOR_SUCCESS)
                if self.db_cog: win_embed.add_field(name="Your Total Score", value=f"**{new_total_score}** points")
                else: win_embed.set_footer(text="Score save error.")

                edited_message = False
                last_msg_id = active_loop_data.get("last_round_message_id")
                if last_msg_id:
                    try:
                        msg_to_edit = await message.channel.fetch_message(last_msg_id)
                        await msg_to_edit.edit(content=None, embed=win_embed, view=None)
                        active_loop_data["last_round_message_id"] = msg_to_edit.id # Keep ID
                        edited_message = True
                    except Exception as e:
                        log.warning(f"Failed edit msg {last_msg_id} for win r{current_r}: {e}. Sending new.")

                if not edited_message:
                    try:
                        sent_msg = await message.channel.send(embed=win_embed)
                        active_loop_data["last_round_message_id"] = sent_msg.id # Store new ID
                    except Exception as e:
                        log.exception(f"Failed sending new win message for {user_id}: {e}")

            else: # Correct answer but time_taken > limit
                log.warning(f"User {user_name} correct r{current_r} but too late ({time_taken:.2f}s)")
                # Timeout task likely already set the event and sent message. No action needed here.
                pass

        else: # Event was already set - this player was too late for this round
            log.debug(f"User {message.author} correct r{active_loop_data.get('current_round', '?')} but event already set.")


async def setup(bot: commands.Bot):
    db_cog = bot.get_cog("Database")
    if db_cog is None:
        log.critical("Database Cog required by Unscramble Cog not loaded.")
        raise commands.ExtensionFailed("unscramble", "Database Cog not found.")
    await bot.add_cog(UnscrambleCog(bot))
    log.info("Unscramble Cog added to bot.")
