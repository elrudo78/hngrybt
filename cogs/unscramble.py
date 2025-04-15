# cogs/unscramble.py
# Game logic for auto-running Unscramble loop with auto-hints.
# Incorporates:
# 1. Automatic leaderboard display every N rounds.
# 2. End-of-game leaderboard display.
# 3. Integration with DatabaseCog storing usernames.

import discord
from discord.ext import commands
import random
import time # <<< CHANGE >>> Added time import
import os # <<< CHANGE >>> Make sure os is imported
import asyncio
import logging
import config
from .database import DatabaseCog # Database Cog now provides usernames

log = logging.getLogger(__name__)

class UnscrambleCog(commands.Cog, name="Unscramble"):
    """Auto-running Unscramble game loop with automatic hints"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_loops = {}
        # <<< CHANGE >>> Store multiple word lists and a combined one
        self.word_lists = {}  # Dict: {"theme_name": [WORD, ...], ...}
        self.combined_word_list = [] # List: [WORD, ...] (all words from all lists)
        # <<< CHANGE >>> Ensure db_cog is fetched correctly
        self.db_cog = self.bot.get_cog("Database") # Get it during init

        if not self.db_cog:
            log.critical("!!! Database Cog not found during Unscramble init! Leaderboard features disabled. !!!")
        self._load_words()
        log.info("Unscramble Cog initialized.")

    # <<< CHANGE >>> Overhaul _load_words completely
    def _load_words(self):
        """Loads words from all .txt files in the configured folder."""
        self.word_lists = {} # Reset caches
        self.combined_word_list = []
        loaded_files_count = 0
        total_words_count = 0

        if not os.path.isdir(config.WORDS_FOLDER):
            log.error(f"Word list folder not found or is not a directory: '{config.WORDS_FOLDER}'. No words loaded.")
            # You might want to create it here too, though config.py attempts it
            # Or just ensure the bot fails gracefully later if no words are loaded.
            return # Stop loading if folder doesn't exist

        log.info(f"Loading word lists from folder: '{config.WORDS_FOLDER}'...")
        try:
            for filename in os.listdir(config.WORDS_FOLDER):
                if filename.lower().endswith(".txt"):
                    theme_name = filename[:-4].lower() # Theme name is filename without .txt, lowercase
                    filepath = os.path.join(config.WORDS_FOLDER, filename)
                    try:
                        with open(filepath, "r", encoding='utf-8') as f:
                            # Read, strip whitespace, filter empty lines, convert to uppercase
                            words_in_file = [line.strip().upper() for line in f if line.strip()]

                        if words_in_file:
                            self.word_lists[theme_name] = words_in_file
                            self.combined_word_list.extend(words_in_file) # Add to the combined list
                            log.info(f"  -> Loaded theme '{theme_name}' with {len(words_in_file)} words from '{filename}'.")
                            loaded_files_count += 1
                            total_words_count += len(words_in_file)
                        else:
                            log.warning(f"  -> Skipped empty or invalid word list file: '{filename}'")
                    except FileNotFoundError:
                        # Should not happen with listdir, but belt-and-suspenders
                        log.error(f"  -> File not found during read (unexpected): '{filepath}'")
                    except Exception as e:
                        log.exception(f"  -> Failed to read or process file '{filepath}': {e}")

            # After loop, check if anything was loaded
            if not self.word_lists:
                log.critical(f"No valid word lists loaded from '{config.WORDS_FOLDER}'. Unscramble game will not work.")
                # Optionally add a dummy list to prevent crashes later, but logging is key
                # self.word_lists["error"] = ["SETUP_ERROR"]
                # self.combined_word_list = ["SETUP_ERROR"]
            else:
                # Ensure combined list has unique words if desired (optional)
                # self.combined_word_list = list(set(self.combined_word_list))
                # total_words_count = len(self.combined_word_list) # Update count if using set
                log.info(f"Finished loading: {loaded_files_count} themes, {total_words_count} total words.")

        except Exception as e:
            log.exception(f"An unexpected error occurred while scanning the word list folder '{config.WORDS_FOLDER}': {e}")

    def _create_hint_string(self, word, revealed_indices):
        """Creates the hint string like W O R _"""
        hint_display = []
        for i, letter in enumerate(word):
            if i in revealed_indices: hint_display.append(f"**{letter}**")
            else: hint_display.append("＿") # Fullwidth underscore U+FF3F
        return " ".join(hint_display)

    # <<< CHANGE >>> Helper function for formatting leaderboard embed (reduces duplication)
    async def _format_leaderboard_embed(self, title: str, footer_text: str, leaderboard_data: dict) -> discord.Embed | None:
        """Formats the top 10 leaderboard embed using cached data."""
        if not leaderboard_data:
            log.debug("Leaderboard data is empty, cannot format embed.")
            return None # Or return an embed saying it's empty

        # Sort by score descending. leaderboard_data is {user_id: {'name': name, 'score': score}}
        # We need to convert it to a list of tuples for sorting: [(user_id, {'name': name, 'score': score}), ...]
        try:
             sorted_leaderboard = sorted(
                 leaderboard_data.items(),
                 key=lambda item: item[1].get('score', 0), # Sort by score in the nested dict
                 reverse=True
             )
        except Exception as e:
             log.exception(f"Error sorting leaderboard data: {e} - Data: {leaderboard_data}")
             return None # Cannot proceed if sorting fails


        embed = discord.Embed(title=title, color=config.EMBED_COLOR_INFO)
        lb_text = ""
        rank = 1
        entries_to_show = 10
        displayed_count = 0

        for user_id_key, user_data in sorted_leaderboard[:entries_to_show]:
            # <<< CHANGE >>> Use cached name directly
            user_display_name = user_data.get('name', f"Unknown ({user_id_key})")
            score = user_data.get('score', 0)

            # Only display if score is > 0 (though DB likely handles this)
            if score > 0:
                 lb_text += f"`{rank}.` {user_display_name}: **{score}** points\n"
                 rank += 1
                 displayed_count += 1

        if not lb_text:
            lb_text = "The leaderboard is currently empty or no players have scored."
            # Optional: Change embed color or add a specific field
            # embed.color = config.EMBED_COLOR_WARNING

        embed.description = lb_text
        final_footer = footer_text + f" | Showing top {displayed_count}" if displayed_count > 0 else footer_text
        embed.set_footer(text=final_footer)
        return embed

    async def _game_timeout_task(self, channel: discord.TextChannel, channel_id: int, round_start_time: float, correct_word: str, loop_data: dict):
        """Background task for per-round timeout. Updates loop state."""
        try:
            await asyncio.sleep(config.TIME_LIMIT_SECONDS)

            active_loop_data = self.active_loops.get(channel_id)
            if not active_loop_data: return

            current_round_details = active_loop_data.get("current_round_details")
            if not current_round_details or current_round_details['start_time'] != round_start_time:
                log.debug(f"[Timeout Task {channel_id}] Round ended/changed before timeout.")
                return

            # Process Timeout
            current_r = active_loop_data['current_round']
            log.info(f"[Timeout Task {channel_id}] Round {current_r} timed out. Word: {correct_word}.")

            active_loop_data["consecutive_timeouts"] += 1
            active_loop_data["round_status"] = "TIMEOUT"

            timeout_embed = discord.Embed(
                title=f"⏱️ Time's Up! (Round {current_r})",
                description=f"Nobody guessed the word!\nThe word was **{correct_word}**.",
                color=config.EMBED_COLOR_ERROR
            )

            try: await channel.send(embed=timeout_embed)
            except Exception as e: log.exception(f"[Timeout Task {channel_id}] Error sending timeout msg: {e}")

            # Cancel hint task
            hint_task = current_round_details.get("hint_task_ref")
            if hint_task and not hint_task.done(): hint_task.cancel()

            # Signal main loop
            active_loop_data["round_complete_event"].set()

        except asyncio.CancelledError: log.debug(f"[Timeout Task {channel_id}] Cancelled.")
        except Exception as e: log.exception(f"[Timeout Task {channel_id}] Error: {e}")

    async def _hint_scheduler_task(self, channel: discord.TextChannel, channel_id: int, round_start_time: float, correct_word: str, scrambled_word: str, loop_data: dict):
        """Runs in background, sending hints for the current round."""
        last_hint_time = 0; hints_shown_count = 0
        max_hints = max(0, len(correct_word)//2);
        if len(correct_word) > 1 and max_hints==0: max_hints=1
        current_r = loop_data.get("current_round","?")
        log.debug(f"[Hint Task {channel_id}-{current_r}] Start. Max:{max_hints}. Sched:{config.HINT_SCHEDULE_SECONDS}")
        try:
            for scheduled_time in config.HINT_SCHEDULE_SECONDS:
                # Check active state before sleeping AND after waking up
                active_loop_data=self.active_loops.get(channel_id);
                if not active_loop_data: break
                current_round_details=active_loop_data.get("current_round_details");
                if not current_round_details or current_round_details['start_time']!=round_start_time: break
                if current_round_details['hints_given']>=max_hints: break

                sleep_duration = scheduled_time - last_hint_time
                if sleep_duration<=0: continue
                await asyncio.sleep(sleep_duration); last_hint_time=scheduled_time

                # Recheck state after sleep
                active_loop_data=self.active_loops.get(channel_id);
                if not active_loop_data: break
                current_round_details=active_loop_data.get("current_round_details");
                if not current_round_details or current_round_details['start_time']!=round_start_time: break
                if current_round_details['hints_given']>=max_hints: break

                hints_shown_count = current_round_details['hints_given'] + 1
                log.info(f"[Hint Task {channel_id}-{current_r}] Triggering hint #{hints_shown_count} @ {scheduled_time}s.")

                revealed_indices=current_round_details['revealed_indices']
                available_indices=[i for i in range(len(correct_word)) if i not in revealed_indices]
                if not available_indices: break # Should not happen if max_hints is correct

                index_to_reveal = random.choice(available_indices)
                revealed_indices.add(index_to_reveal)
                current_round_details['hints_given'] = hints_shown_count # Update state

                hint_display_string = self._create_hint_string(correct_word, revealed_indices)
                embed = discord.Embed(title=f"💡 Hint #{hints_shown_count}", description=f"Stuck on **{scrambled_word}**?\n\n# {hint_display_string}", color=config.EMBED_COLOR_HINT)
                try: await channel.send(embed=embed)
                except Exception as e: log.exception(f"[Hint Task {channel_id}-{current_r}] Fail send hint: {e}")

            log.debug(f"[Hint Task {channel_id}-{current_r}] Schedule finish.")
        except asyncio.CancelledError: log.debug(f"[Hint Task {channel_id}-{current_r}] Cancelled.")
        except Exception as e: log.exception(f"[Hint Task {channel_id}-{current_r}] Error: {e}")

    # <<< CHANGE >>> Modify signature to accept *args and parse manually
    @commands.command(name='unscramble', aliases=['us'])
    @commands.has_role(config.MOD_ROLE_NAME)
    @commands.guild_only()
    async def unscramble(self, ctx: commands.Context, *args): # Accept any number of arguments
        """Starts Unscramble. Args: [rounds] [theme] OR [theme]. Uses default theme/infinite rounds if omitted."""
        channel_id = ctx.channel.id

        if channel_id in self.active_loops:
            await ctx.send(embed=discord.Embed(title="⏳ Game Already Running", description="A game is already active in this channel.", color=config.EMBED_COLOR_WARNING))
            return

        # --- Argument Parsing Logic ---
        # <<< CHANGE >>> Start Manual Parsing Block
        parsed_rounds_str = None
        parsed_theme_list = [] # To collect parts of multi-word themes

        if not args:
            # Case: !us (no arguments)
            # Defaults: rounds=infinite, theme=None (will use default theme)
            pass
        elif args[0].isdigit():
            # Case: Starts with a number, assume it's rounds
            # Example: !us 10 OR !us 10 foods OR !us 10 harry potter
            parsed_rounds_str = args[0]
            if len(args) > 1:
                # Anything after the number is the theme
                parsed_theme_list = list(args[1:])
        else:
            # Case: Starts with a non-number, assume it's the theme
            # Example: !us foods OR !us harry potter OR !us foods 10 OR !us harry potter 10
            # Check if the *last* argument is a digit (potential rounds value at the end)
            if len(args) > 1 and args[-1].isdigit():
                parsed_rounds_str = args[-1]
                parsed_theme_list = list(args[:-1]) # Theme is everything except the last arg
            else:
                # No digit at the end, assume all args are the theme
                parsed_theme_list = list(args)
                # rounds remains None (infinite)

        # --- Rounds Validation ---
        target_rounds = float('inf')
        is_infinite = True
        if parsed_rounds_str is not None:
            try:
                num_rounds = int(parsed_rounds_str)
                if num_rounds <= 0:
                    # Handle non-positive numbers explicitly
                    await ctx.send(embed=discord.Embed(description=f"Invalid number of rounds: `{num_rounds}`. Rounds must be a positive number.", color=config.EMBED_COLOR_ERROR))
                    return
                target_rounds = num_rounds
                is_infinite = False
            except ValueError:
                # This should technically not happen if .isdigit() was true, but belt-and-suspenders
                await ctx.send(embed=discord.Embed(description=f"Invalid number format for rounds: `{parsed_rounds_str}`.", color=config.EMBED_COLOR_ERROR))
                return

        # --- Theme Reconstruction ---
        # Join the collected theme words, handle if list is empty
        theme = " ".join(parsed_theme_list).strip() if parsed_theme_list else None
        # <<< CHANGE >>> End Manual Parsing Block

        # --- Theme Selection & Word List Preparation ---
        # <<< CHANGE >>> Logic to select word list based on theme
        active_word_list = []
        chosen_theme_name = "Unknown" # Default display name

        if not self.word_lists: # Check if any words were loaded at all
             await ctx.send(embed=discord.Embed(description="❌ Error: No word lists are loaded. Cannot start game.", color=config.EMBED_COLOR_ERROR))
             log.error(f"Attempted to start game in {channel_id} but no word lists loaded.")
             return

        available_themes = list(self.word_lists.keys())

        if theme:
            # User specified a theme (or we parsed one)
            clean_theme = theme.lower() # Already joined, just lower()
            if clean_theme in self.word_lists:
                active_word_list = self.word_lists[clean_theme]
                chosen_theme_name = clean_theme.capitalize() # For display
                log.info(f"Theme specified: '{clean_theme}'. Using corresponding word list ({len(active_word_list)} words).")
            else:
                # Invalid theme specified
                themes_str = ", ".join(f"`{t}`" for t in available_themes) if available_themes else "None available"
                await ctx.send(embed=discord.Embed(
                    title="❓ Theme Not Found",
                    description=f"Could not find the theme: `{theme}`.\nAvailable themes: {themes_str}",
                    color=config.EMBED_COLOR_ERROR
                ))
                return
        else:
            # No theme specified, use default logic
            if config.DEFAULT_THEME_NAME and config.DEFAULT_THEME_NAME.lower() in self.word_lists:
                # Use the specific default theme file
                default_key = config.DEFAULT_THEME_NAME.lower()
                active_word_list = self.word_lists[default_key]
                chosen_theme_name = default_key.capitalize() # For display
                log.info(f"No theme specified. Using default theme: '{default_key}' ({len(active_word_list)} words).")
            elif self.combined_word_list:
                 # Fallback: Default theme not found/specified, use combined list if available
                 active_word_list = self.combined_word_list
                 chosen_theme_name = "All Themes"
                 log.info(f"No theme specified, default '{config.DEFAULT_THEME_NAME}' not found/set. Using combined list ({len(active_word_list)} words).")
            # else: If we reach here, something went wrong loading, handled by initial check

        # Final check if the selected list is empty
        if not active_word_list:
             await ctx.send(embed=discord.Embed(description=f"❌ Error: The selected theme ('{chosen_theme_name}') resulted in an empty word list. Cannot start game.", color=config.EMBED_COLOR_ERROR))
             log.error(f"Attempted to start game in {channel_id} with theme '{chosen_theme_name}' but list was empty.")
             return

       # --- Prepare and Start Loop ---
        loop_data = {
            "loop_task": None, "target_rounds": target_rounds, "current_round": 0,
            "consecutive_timeouts": 0, "round_complete_event": asyncio.Event(),
            "round_status": None, "channel_id": channel_id, "guild_id": ctx.guild.id,
            "last_auto_lb_time": 0.0,
            # <<< CHANGE >>> Pass the selected list and theme name to the loop
            "active_word_list": active_word_list,
            "theme_name": chosen_theme_name
        }

        log.info(f"Starting game loop: Channel {channel_id}, Guild {ctx.guild.id}, Rounds: {'Infinite' if is_infinite else target_rounds}, Theme: '{chosen_theme_name}', Requested by {ctx.author} ({ctx.author.id})")
        game_loop_task = self.bot.loop.create_task( self._channel_game_loop(ctx, loop_data), name=f"GameLoop-{channel_id}")
        loop_data["loop_task"] = game_loop_task
        self.active_loops[channel_id] = loop_data

        start_msg = f"✅ Unscramble game started by {ctx.author.mention} for **{'infinite' if is_infinite else target_rounds}** rounds!"
        start_msg += f"\n**Theme:** {chosen_theme_name}" # Add theme info
        await ctx.send(embed=discord.Embed(description=start_msg, color=config.EMBED_COLOR_SUCCESS))

    async def _channel_game_loop(self, ctx: commands.Context, loop_data: dict):
        """Main async task managing the auto-running game loop for a channel."""
        channel_id = loop_data["channel_id"]
        # <<< CHANGE >>> Get word list and theme name from loop_data
        active_word_list = loop_data.get("active_word_list", []) # Get the specific list for this game
        theme_name = loop_data.get("theme_name", "Unknown")      # Get the theme name for display
        round_delay = 5.0 # Base delay between rounds
        round_timeout_task = None
        round_hint_task = None

        # <<< CHANGE >>> Add check here too, although command should prevent it
        if not active_word_list:
            log.error(f"[Loop {channel_id}] Game loop started but active_word_list is empty! Theme: '{theme_name}'. Aborting.")
            await ctx.send(embed=discord.Embed(description="❌ Critical Error: Game cannot start with an empty word list.", color=config.EMBED_COLOR_ERROR))
            # Need to clean up the loop data if we abort here
            self.active_loops.pop(channel_id, None)
            return
        # <<< CHANGE >>> Ensure db_cog is available within the loop
        if not self.db_cog:
            log.error(f"[Loop {channel_id}] Database Cog not available at loop start. Leaderboard features disabled.")
            # Optionally send a message to the channel?
            # await ctx.send("Warning: Leaderboard connection error. Scores may not save/display.")

        try:
            while True:
                loop_data["current_round"] += 1
                current_r = loop_data["current_round"]
                target_r = loop_data["target_rounds"]
                timeouts = loop_data["consecutive_timeouts"]
                log.info(f"[Loop {channel_id}] Starting Round {current_r} (Target: {'Inf' if target_r == float('inf') else int(target_r)}, Consecutive Timeouts: {timeouts})")

                # --- Check End Conditions ---
                if current_r > target_r:
                    log.info(f"[Loop {channel_id}] Target rounds ({int(target_r)}) reached.")
                    await ctx.send(embed=discord.Embed(title="🏁 Game Finished 🏁", description=f"Completed the target of {int(target_r)} rounds!", color=config.EMBED_COLOR_INFO))
                    break # Exit loop

                if timeouts >= 2:
                    log.warning(f"[Loop {channel_id}] Stopping game due to {timeouts} consecutive timeouts.")
                    await ctx.send(embed=discord.Embed(title="😴 Game Stopped", description=f"Stopping due to inactivity.", color=config.EMBED_COLOR_WARNING))
                    break # Exit loop

                # --- Reset Round State ---
                loop_data["round_complete_event"].clear()
                loop_data["round_status"] = None
                round_timeout_task = None
                round_hint_task = None

                try:
                    # --- Prepare Round ---
                    original_word = random.choice(active_word_list)
                    scrambled_word = original_word
                    # Ensure scramble happens for words > 1 length
                    while len(original_word) > 1 and scrambled_word == original_word:
                        word_letters = list(original_word)
                        random.shuffle(word_letters)
                        scrambled_word = "".join(word_letters)

                    current_round_details = {
                         "word": original_word, "start_time": time.time(),
                         "revealed_indices": set(), "hints_given": 0,
                         "loop_data_ref": loop_data, # Reference back if needed
                         "timeout_task_ref": None, "hint_task_ref": None
                    }
                    loop_data["current_round_details"] = current_round_details

                    # --- Send Round Embed ---
                    round_title = f"🧩 Round {current_r}" + (f" / {int(target_r)}" if target_r != float('inf') else "")
                    round_desc = f"Theme: **{theme_name}**\nUnscramble the word below!\n\n# **{scrambled_word}**\n\n*Time Limit: {config.TIME_LIMIT_SECONDS} seconds. Hints appear automatically.*"
                    round_embed = discord.Embed(title=round_title, description=round_desc, color=config.EMBED_COLOR_DEFAULT)
                    if target_r != float('inf'): round_embed.set_footer(text=f"Game Progress: {current_r}/{int(target_r)}")

                    try: await ctx.send(embed=round_embed)
                    except discord.HTTPException as e:
                         log.exception(f"[Loop {channel_id}] Failed to send round start message (Round {current_r}): {e}")
                         # Decide if loop should continue or break here? Maybe break.
                         await ctx.send(embed=discord.Embed(description="❌ Error sending message. Stopping game.", color=config.EMBED_COLOR_ERROR))
                         break
                    except Exception as e: # Catch broader exceptions just in case
                         log.exception(f"[Loop {channel_id}] Unexpected error sending round start message (Round {current_r}): {e}")
                         await ctx.send(embed=discord.Embed(description="❌ Unexpected error. Stopping game.", color=config.EMBED_COLOR_ERROR))
                         break


                    # --- Start Background Tasks ---
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

                    # --- Wait for Round End (Win/Timeout) ---
                    await loop_data["round_complete_event"].wait()
                    log.debug(f"[Loop {channel_id}] Round {current_r} complete event received. Status: {loop_data.get('round_status')}")

                except Exception as round_e:
                    log.exception(f"[Loop {channel_id}] Unhandled error within round {current_r} setup/wait: {round_e}")
                    try: await ctx.send(embed=discord.Embed(title=f"⚠️ Error in Round {current_r}", description="An unexpected error occurred. Trying to proceed to the next round...", color=config.EMBED_COLOR_ERROR))
                    except Exception: pass # Ignore if can't send error msg
                finally:
                    # Ensure tasks are cancelled and details cleared regardless of how round ended
                    if round_timeout_task and not round_timeout_task.done(): round_timeout_task.cancel()
                    if round_hint_task and not round_hint_task.done(): round_hint_task.cancel()
                    loop_data.pop("current_round_details", None) # Remove details for the completed round


                # <<< CHANGE: Revised Automatic Leaderboard, Toast & Delay Logic >>>
                should_continue_loop = (loop_data["current_round"] < loop_data["target_rounds"]) and (loop_data["consecutive_timeouts"] < 2)

                # Determine if the round that *just finished* was an interval round
                is_current_round_lb_round = (current_r % config.LEADERBOARD_INTERVAL == 0) and current_r > 0

                current_inter_round_delay = round_delay # Start with base delay

                # 1. Show Leaderboard if appropriate
                if is_current_round_lb_round and self.db_cog:
                    log.info(f"[Loop {channel_id}] Attempting to show automatic leaderboard after round {current_r}.")
                    try:
                        leaderboard_data = await self.db_cog.get_leaderboard_data()
                        lb_embed = await self._format_leaderboard_embed(
                             title=f"🏆 Leaderboard Update (After R{current_r}) 🏆",
                             footer_text=f"Broadcasts every {config.LEADERBOARD_INTERVAL} rounds.",
                             leaderboard_data=leaderboard_data
                        )
                        if lb_embed:
                             await ctx.send(embed=lb_embed)
                             loop_data["last_auto_lb_time"] = time.time() # Record time LB was shown
                             log.info(f"[Loop {channel_id}] Automatic leaderboard sent.")
                             # <<< CHANGE >>> Add extra delay *after* showing the LB
                             current_inter_round_delay += config.LEADERBOARD_EXTRA_DELAY
                             log.debug(f"[Loop {channel_id}] Added extra delay ({config.LEADERBOARD_EXTRA_DELAY}s) because LB was shown.")
                        else:
                            log.info(f"[Loop {channel_id}] Automatic leaderboard embed was None (likely empty data).")
                    except Exception as e:
                         log.exception(f"[Loop {channel_id}] Error fetching/sending auto-leaderboard: {e}")

                # 2. Send 'Next Round' toast ONLY if the loop continues AND LB wasn't just shown
                if should_continue_loop and not is_current_round_lb_round:
                    try:
                        log.debug(f"[Loop {channel_id}] Sending 'next round' toast (LB not shown this interval).")
                        toast_delete_after = max(3.0, current_inter_round_delay - 0.5) # Adjust delete timer based on delay
                        await ctx.send(embed=discord.Embed(description="⏭️ Next round starting soon...", color=config.EMBED_COLOR_INFO), delete_after=toast_delete_after)
                    except Exception as e:
                        log.warning(f"[Loop {channel_id}] Failed sending 'next round' toast message: {e}")
                elif is_current_round_lb_round:
                    log.debug(f"[Loop {channel_id}] Suppressing 'next round' toast because leaderboard was just displayed.")


                # 3. Perform the inter-round delay IF the loop should continue
                if should_continue_loop:
                     log.debug(f"[Loop {channel_id}] Sleeping for {current_inter_round_delay:.1f} seconds before round {current_r + 1}.")
                     await asyncio.sleep(current_inter_round_delay)
                # else: Loop is ending, no sleep needed


        except asyncio.CancelledError:
            log.info(f"[Loop {channel_id}] Game loop task was cancelled externally (e.g., !stop command).")
            # Send stop message only if cancellation was likely external, not from break conditions
            if loop_data.get("round_status") != "STOPPED_INTERNAL": # Add a flag if needed for more clarity
                 try: await ctx.send(embed=discord.Embed(description="🛑 Game has been stopped.", color=config.EMBED_COLOR_WARNING))
                 except Exception: pass
        except Exception as loop_e:
            log.exception(f"[Loop {channel_id}] CRITICAL error in main game loop: {loop_e}")
            try: await ctx.send(embed=discord.Embed(title="💥 Critical Error!", description="The game encountered a critical error and had to stop.", color=config.EMBED_COLOR_ERROR))
            except Exception: pass
        finally:
            log.info(f"[Loop {channel_id}] Entering final cleanup for game loop.")

            # <<< CHANGE: Final Leaderboard Display >>>
            try:
                 # Check anti-spam: More than N seconds since last auto-LB?
                 time_since_last_lb = time.time() - loop_data.get('last_auto_lb_time', 0)
                 if time_since_last_lb > config.LEADERBOARD_ANTI_SPAM_SECONDS:
                     log.info(f"[Loop {channel_id}] Attempting to show final leaderboard (Last LB: {time_since_last_lb:.0f}s ago > {config.LEADERBOARD_ANTI_SPAM_SECONDS}s).")
                     if self.db_cog:
                         leaderboard_data = await self.db_cog.get_leaderboard_data()
                         final_lb_embed = await self._format_leaderboard_embed(
                             title="🏆 Final Game Leaderboard 🏆",
                             footer_text="Game Over!",
                             leaderboard_data=leaderboard_data
                         )
                         if final_lb_embed:
                              await ctx.send(embed=final_lb_embed)
                              log.info(f"[Loop {channel_id}] Final leaderboard sent.")
                         else:
                              log.info(f"[Loop {channel_id}] Final leaderboard embed was None.")
                     else:
                         log.error(f"[Loop {channel_id}] Cannot show final leaderboard: Database Cog not available.")
                 else:
                      log.info(f"[Loop {channel_id}] Final leaderboard skipped due to anti-spam check (Last LB shown {time_since_last_lb:.0f}s ago).")
            except Exception as e:
                 log.exception(f"[Loop {channel_id}] Error displaying final leaderboard: {e}")

            # Final cleanup: Remove from active loops dictionary
            removed_loop = self.active_loops.pop(channel_id, None)
            if removed_loop:
                 log.info(f"[Loop {channel_id}] Successfully removed loop data from active_loops.")
            else:
                 log.warning(f"[Loop {channel_id}] Attempted to remove loop data, but it was already gone from active_loops.")


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for answers and processes the first winner for an active loop."""
        # Basic checks: ignore self, DMs, commands
        if message.author == self.bot.user or not message.guild or message.content.startswith(config.COMMAND_PREFIX):
            return

        channel_id = message.channel.id
        # Quick check: is there *any* active loop in this channel?
        active_loop_data = self.active_loops.get(channel_id)
        if not active_loop_data:
            return

        # Deeper check: is there *current round data*? (Handles edge case between rounds)
        current_round_details = active_loop_data.get("current_round_details")
        if not current_round_details:
            return

        # Get the correct word for comparison
        correct_word = current_round_details.get("word")
        if not correct_word: # Should not happen if round details exist
            log.error(f"Missing 'word' in current_round_details for channel {channel_id}")
            return

        # The actual guess check (case-insensitive)
        if message.content.strip().upper() != correct_word:
            return

        # --- Correct Answer Received ---

        # Critical check: Is the round completion event *already set*? If so, someone else was faster.
        if not active_loop_data["round_complete_event"].is_set():
            # --- We are the FIRST winner for this round! ---
            # Set the event immediately to prevent race conditions
            active_loop_data["round_status"] = "WIN"
            active_loop_data["round_complete_event"].set()

            start_time = current_round_details["start_time"]
            time_taken = time.time() - start_time
            user_id = message.author.id
            user_name = message.author.display_name # Get current display name for message
            current_r = active_loop_data["current_round"]
            log.info(f"Correct Answer! User: {user_name} ({user_id}) in Channel: {channel_id}, Round: {current_r}. Time: {time_taken:.2f}s")

            # Cancel this round's timeout and hint tasks
            tasks_to_cancel = [current_round_details.get('timeout_task_ref'), current_round_details.get('hint_task_ref')]
            cancelled_task_count = 0
            for task in tasks_to_cancel:
                 if task and not task.done():
                      try:
                          task.cancel()
                          cancelled_task_count += 1
                      except Exception as e:
                           log.error(f"Error cancelling task during win processing (Round {current_r}, Channel {channel_id}): {e}")
            log.debug(f"Cancelled {cancelled_task_count} background tasks for round {current_r}.")

            # Reset consecutive timeouts on a successful guess
            active_loop_data["consecutive_timeouts"] = 0

            # --- Calculate Points & Update Score ---
            points_earned = 0
            new_total_score = 0 # Initialize score

            # Use Decimal for points if more precision needed, but int is fine here
            if time_taken <= config.TIME_LIMIT_SECONDS: # Ensure they were within time limit
                if time_taken <= 10: points_earned = 100
                elif time_taken <= 20: points_earned = 85
                elif time_taken <= 30: points_earned = 70
                elif time_taken <= 40: points_earned = 55
                elif time_taken <= 50: points_earned = 40
                else: points_earned = 25 # Score for 50.01s to 60.00s

                if self.db_cog:
                    try:
                        # <<< CHANGE >>> update_score now returns the new total score
                        new_total_score = await self.db_cog.update_score(user_id, points_earned)
                        log.info(f"Score updated for {user_id}. New total: {new_total_score}")
                    except Exception as db_e:
                        log.exception(f"Error calling update_score for {user_id}: {db_e}")
                        points_earned = -1 # Indicate score save error
                else:
                    log.error(f"Database Cog not available. Cannot update score for user {user_id}.")
                    points_earned = -1 # Indicate score save error

                # --- Send Win Message ---
                win_desc = f"You unscrambled **{correct_word}** in **{time_taken:.2f}** seconds!\n"
                if points_earned > 0:
                    win_desc += f"You earned **{points_earned}** points."
                elif points_earned == 0: # Should not happen with current logic, but good practice
                     win_desc += "No points awarded for this round."
                else: # points_earned == -1
                     win_desc += "\n⚠️ There was an issue saving your score."

                win_embed = discord.Embed(title=f"🎉 Correct, {user_name}! 🎉", description=win_desc, color=config.EMBED_COLOR_SUCCESS)

                # Add total score if it was successfully calculated/retrieved
                if points_earned != -1 and self.db_cog:
                    win_embed.add_field(name="Your New Total Score", value=f"🏆 **{new_total_score}** points")

                win_embed.set_footer(text=f"Round {current_r} completed.")

                try:
                    await message.channel.send(embed=win_embed)
                except Exception as e:
                    log.exception(f"Failed to send win message for user {user_id} in channel {channel_id}: {e}")

            else:
                # This case should technically be impossible if timeout task works correctly,
                # but log it just in case.
                log.warning(f"User {user_name} ({user_id}) provided correct answer for round {current_r} but time_taken ({time_taken:.2f}s) exceeded limit ({config.TIME_LIMIT_SECONDS}s). Event was somehow not set by timeout task.")
                # Don't send a message here, as the timeout message should have already been sent.

        else:
            # Another user already won, this guess is too late.
            log.debug(f"User {message.author} ({message.author.id}) guessed correctly for round {active_loop_data.get('current_round', '?')} but event was already set.")
            # Optionally react to the message? e.g., with a clock emoji? (Could be noisy)
            # try: await message.add_reaction("⏱️") # Example reaction
            # except: pass


async def setup(bot: commands.Bot):
    # <<< CHANGE >>> Check for DB Cog explicitly at setup
    db_cog = bot.get_cog("Database")
    if db_cog is None:
        log.critical("FATAL: Database Cog is required by Unscramble Cog but was not found/loaded.")
        # Depending on strictness, either raise error or allow cog to load with warnings
        raise commands.ExtensionFailed("unscramble", "Setup failed: Database Cog not found.")
    else:
        await bot.add_cog(UnscrambleCog(bot))
        log.info("Unscramble Cog added to bot.")
