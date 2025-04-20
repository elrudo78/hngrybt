# cogs/global_utils/help_cog.py
# Contains the global help command for the bot.

import discord
from discord.ext import commands
import logging
import config  # For COMMAND_PREFIX, MOD_ROLE_NAME

log = logging.getLogger(__name__)

class HelpCog(commands.Cog, name="Help"):
    """Provides a dynamic, global help command."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Store mapping of game cog names to display names & command prefixes if needed
        # This can be expanded as more games are added
        self.game_info = {
            "UnscrambleAdmin": {"display_name": "Unscramble Admin", "prefix": "us_"},
            "UnscrambleGeneral": {"display_name": "Unscramble General", "prefix": "us_"},
            "Unscramble": {"display_name": "Unscramble Game", "prefix": ""}, # Main game command prefix is empty
            # Add Riddle info later:
            # "RiddlesAdmin": {"display_name": "Riddles Admin", "prefix": "riddle_"},
            # "RiddlesGeneral": {"display_name": "Riddles General", "prefix": "riddle_"},
            # "Riddles": {"display_name": "Riddles Game", "prefix": ""},
        }
        log.info("Global Help Cog initialized.")


    @commands.command(name='help', aliases=['h', 'commands'])
    @commands.guild_only() # Keep in guilds for simplicity
    # No role restriction - help should be public
    async def help_command(self, ctx: commands.Context, *, command_name: str = None):
        """Shows help for all commands or a specific command."""

        log.info(f"Help command requested by {ctx.author} in guild {ctx.guild.id}. Specific command: '{command_name}'")

        prefix = config.COMMAND_PREFIX

        # If a specific command is requested
        if command_name:
            command = self.bot.get_command(command_name)
            if command and not command.hidden:
                # Found the command, show detailed help
                embed = discord.Embed(
                    title=f"ℹ️ Help: `{prefix}{command.qualified_name}`",
                    description=command.help or "No description available.",
                    color=config.EMBED_COLOR_INFO # Use a specific help color maybe?
                )
                # Format usage
                usage = f"`{prefix}{command.qualified_name}"
                if command.signature:
                    usage += f" {command.signature}`"
                else:
                    usage += "`"
                embed.add_field(name="Usage", value=usage, inline=False)

                # Add aliases if they exist
                if command.aliases:
                    aliases_str = ", ".join(f"`{prefix}{alias}`" for alias in command.aliases)
                    embed.add_field(name="Aliases", value=aliases_str, inline=False)

                # Check for role requirement (Note: This is a basic check, might not cover all check types)
                role_check = next((check for check in command.checks if check.__qualname__.startswith('has_role')), None)
                if role_check:
                     # Try to extract the role name if possible (fragile method)
                     try:
                         role_name = role_check.__closure__[0].cell_contents
                         embed.add_field(name="Requires Role", value=f"`{role_name}`", inline=False)
                     except (AttributeError, IndexError):
                          embed.add_field(name="Requires Role", value="Yes (Check specific permissions)", inline=False)


                await ctx.send(embed=embed)
                return
            else:
                # Command not found or hidden
                await ctx.send(f"❓ Command `{command_name}` not found or is hidden. Try `{prefix}help` for a list.", delete_after=15)
                return

        # --- General Help (List all commands) ---
        embed = discord.Embed(title="🧩 Bot Commands Help 🧩",
                              description=f"Here are the available commands. Use `{prefix}help [command_name]` for details.",
                              color=config.EMBED_COLOR_DEFAULT)
        try: embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        except Exception: pass # Ignore if avatar fetch fails

        # Group commands by Cog/Category
        cogs_commands = {} # {cog_display_name: [command_list_string, requires_role_bool]}

        for cog_name, cog in self.bot.cogs.items():
            # Skip utility cogs or cogs with no commands / only hidden commands
            if cog_name in ["Help", "ErrorHandler", "UnscrambleDB", "RiddlesDB"]: # Adjust as needed
                continue

            command_list = []
            cog_requires_mod = False # Assume false unless a command requires it

            for command in cog.get_commands():
                if not command.hidden: # Don't show hidden commands (like reload)
                    # Basic check if any command in the cog requires the mod role
                    if any(check.__qualname__.startswith('has_role') for check in command.checks):
                         cog_requires_mod = True

                    # Add command to list
                    cmd_str = f"`{prefix}{command.name}`"
                    # Optional: Add brief description if available and short enough
                    # if command.short_doc:
                    #    cmd_str += f" - {command.short_doc}"
                    command_list.append(cmd_str)

            if command_list:
                # Get display name and prefix info from our mapping
                info = self.game_info.get(cog_name, {"display_name": cog.qualified_name, "prefix": "?"}) # Fallback to cog name
                display_name = info["display_name"]

                # Store command list string and role requirement
                cogs_commands[display_name] = ["\n".join(sorted(command_list)), cog_requires_mod]


        # Add fields to the embed, sorted by display name
        if not cogs_commands:
             embed.description += "\n\nNo accessible commands found."
        else:
             sorted_cogs = sorted(cogs_commands.items())
             for display_name, (cmd_list_str, requires_mod) in sorted_cogs:
                 field_name = f"--- {display_name} ---"
                 if requires_mod:
                      field_name += f" (Requires '{config.MOD_ROLE_NAME}')" # Indicate role needed for *some* commands in group
                 embed.add_field(name=field_name, value=cmd_list_str, inline=False)


        embed.set_footer(text="Let the games begin!")
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    # Check dependencies if any (none needed for this basic help)
    await bot.add_cog(HelpCog(bot))
    log.info("Global Help Cog added to bot.")
