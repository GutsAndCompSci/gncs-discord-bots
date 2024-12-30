import discord
from discord import app_commands
import logging
import json
import os
from datetime import datetime, timedelta
import asyncio
from typing import Optional
import re
import time

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

activity = discord.Activity(type=discord.ActivityType.watching, name="That Ship Over There")
client = discord.Client(intents=intents, activity=activity)
starred_messages = set()
tree = discord.app_commands.CommandTree(client)

GUILD_ID = 0
ROLES_FILE = "roles.json"
BANS_FILE = "bans.json"
MUTES_FILE = "mutes.json"
WARNINGS_FILE = "warnings.json"
BANNED_WORDS = "banned_words.json"
NOTES_FILE = "notes.json"
STAR_EMOJI = '⭐'
STARBOARD_CHANNEL_ID = 0
WELCOME_CHANNEL_ID = 0

log_capture = []

class LogHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        log_capture.append(log_entry)
        # keep only the last 100 log entries for recent logs
        if len(log_capture) > 100:
            log_capture.pop(0)

log_handler = LogHandler()
log_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
logging.getLogger().addHandler(log_handler)

banned_word_patterns = [re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE) for word in BANNED_WORDS]
starred_messages = set()

def load_data(file_name):
    if not os.path.exists(file_name):
        return {}
    with open(file_name, "r") as f:
        return json.load(f)

def save_data(file_name, data):
    with open(file_name, "w") as f:
        json.dump(data, f, indent=4)

for file_name in [ROLES_FILE, BANS_FILE, MUTES_FILE, WARNINGS_FILE, BANNED_WORDS, NOTES_FILE]:
    if not os.path.exists(file_name):
        with open(file_name, "w") as f:
            json.dump({}, f)

@client.event
async def on_ready():
    await tree.sync()
    logging.info("Bot is ready and commands are synced globally!")
    await schedule_unbans()

async def schedule_unbans():
    bans_data = load_data(BANS_FILE)
    for user_id, unban_time_str in bans_data.items():
        unban_time = datetime.fromisoformat(unban_time_str)
        now = datetime.now()
        if unban_time > now:
            delay = (unban_time - now).total_seconds()
            client.loop.create_task(unban_user(user_id, delay))

async def unban_user(user_id, delay):
    await asyncio.sleep(delay)
    guild = client.get_guild(GUILD_ID)
    user = await client.fetch_user(user_id)
    await guild.unban(user)
    bans_data = load_data(BANS_FILE)
    if str(user_id) in bans_data:
        del bans_data[str(user_id)]
        save_data(BANS_FILE, bans_data)

@tree.command(name="roleadd", description="Add a role to a member")
@app_commands.describe(member="The member to add a role to", role="The role to add")
async def roleadd(interaction: discord.Interaction, member: discord.Member, role: discord.Role):
    if interaction.user.guild_permissions.manage_roles:
        await member.add_roles(role)
        roles_data = load_data(ROLES_FILE)
        if str(member.id) not in roles_data:
            roles_data[str(member.id)] = []
        if role.id not in roles_data[str(member.id)]:
            roles_data[str(member.id)].append(role.id)
        save_data(ROLES_FILE, roles_data)
        await interaction.response.send_message(f"Role {role.name} added to {member.mention}")
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@tree.command(name="ban", description="Ban a member")
@app_commands.describe(member="The member to ban", duration="Duration of the ban", reason="The reason for the ban")
@app_commands.choices(duration=[
    app_commands.Choice(name="1 day", value="1d"),
    app_commands.Choice(name="7 days", value="7d"),
    app_commands.Choice(name="14 days", value="14d"),
    app_commands.Choice(name="Permanent", value="Permanent")
])
async def ban(interaction: discord.Interaction, member: discord.Member, duration: app_commands.Choice[str], reason: Optional[str] = "No reason provided"):
    if interaction.user.guild_permissions.ban_members:
        await member.send(f"You have been banned for: {duration.value} because of {reason}\n-# To appeal, click [here](<https://example.com>)") # input your appeals form here
        await member.ban(reason=reason)
        await interaction.response.send_message(f"{member.mention} has been banned for: {reason} ({duration.name})")
        if duration.value != "Permanent":
            now = datetime.now()
            if duration.value == "1d":
                unban_time = now + timedelta(days=1)
            elif duration.value == "7d":
                unban_time = now + timedelta(days=7)
            elif duration.value == "14d":
                unban_time = now + timedelta(days=14)
            bans_data = load_data(BANS_FILE)
            bans_data[str(member.id)] = unban_time.isoformat()
            save_data(BANS_FILE, bans_data)
            delay = (unban_time - now).total_seconds()
            client.loop.create_task(unban_user(member.id, delay))
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@tree.command(name="kick", description="Kick a member")
@app_commands.describe(member="The member to kick", reason="The reason for the kick")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided"):
    if interaction.user.guild_permissions.kick_members:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"{member.mention} has been kicked for: {reason}")
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="The member to warn", reason="The reason for the warning")
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    if interaction.user.guild_permissions.manage_messages:
        current_timestamp = int(time.time())

        warnings_data = load_data(WARNINGS_FILE)
        if str(member.id) not in warnings_data:
            warnings_data[str(member.id)] = []

        warnings_data[str(member.id)].append(f"{reason} | <t:{current_timestamp}:R>")

        save_data(WARNINGS_FILE, warnings_data)

        try:
            await member.send(f"You have been warned for: {reason}")
            await interaction.response.send_message(f"{member.mention} has been warned for: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(f"Could not send a DM to {member.mention}.", ephemeral=True)
            return

    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@tree.command(name="warns", description="View warnings for a member")
@app_commands.describe(member="The member to view warnings for")
async def warns(interaction: discord.Interaction, member: discord.Member):
    warnings_data = load_data(WARNINGS_FILE)
    user_warnings = warnings_data.get(str(member.id), [])

    if not user_warnings:
        await interaction.response.send_message(f"{member.display_name} has no warnings.", ephemeral=True)
        return

    embed = discord.Embed(title=f"Warnings for {member.display_name}", color=discord.Color.dark_red())
    for i, warning in enumerate(user_warnings, 1):
        reason, timestamp = warning.rsplit(' | ', 1)
        embed.add_field(name=f"Warning {i}", value=f"**Reason:** {reason}\n**Timestamp:** {timestamp}", inline=False)

    await interaction.response.send_message(embed=embed)

@tree.command(name="delwarn", description="Delete a warning from a member")
@app_commands.describe(member="The member to delete a warning from", warning_index="The index of the warning to delete")
async def delwarn(interaction: discord.Interaction, member: discord.Member, warning_index: int):
    if interaction.user.guild_permissions.manage_messages:
        warnings_data = load_data(WARNINGS_FILE)
        user_warnings = warnings_data.get(str(member.id), [])

        if not user_warnings:
            await interaction.response.send_message(f"{member.display_name} has no warnings.", ephemeral=True)
            return

        if warning_index <= 0 or warning_index > len(user_warnings):
            await interaction.response.send_message(f"Invalid warning index. Please provide a number between 1 and {len(user_warnings)}.", ephemeral=True)
            return

        removed_warning = user_warnings.pop(warning_index - 1)
        save_data(WARNINGS_FILE, warnings_data)

        await interaction.response.send_message(f"Removed warning {warning_index} from {member.mention}: {removed_warning}")
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@tree.command(name="purge", description="Bulk delete messages")
@app_commands.describe(number_of_messages="The number of messages to delete")
async def purge(interaction: discord.Interaction, number_of_messages: int):
    if interaction.user.guild_permissions.manage_messages:
        if number_of_messages <= 0:
            await interaction.response.send_message("Please specify a positive number of messages to delete.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)

        deleted = await interaction.channel.purge(limit=number_of_messages + 1)

        num_deleted = len(deleted)

        await interaction.channel.send(f":white_check_mark: | {num_deleted - 1} messages have been deleted.")
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@tree.command(name="mute", description="Mute a member")
@app_commands.describe(member="The member to mute", reason="The reason for the mute", days="Days to mute", hours="Hours to mute", minutes="Minutes to mute")
async def mute(interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = "No reason provided", days: Optional[int] = 0, hours: Optional[int] = 0, minutes: Optional[int] = 0):
    if interaction.user.guild_permissions.mute_members:
        if days < 0 or hours < 0 or minutes < 0:
            await interaction.response.send_message("Duration values cannot be negative.", ephemeral=True)
            return

        if days == 0 and hours == 0 and minutes == 0:
            minutes = 15

        total_duration = timedelta(days=days, hours=hours, minutes=minutes)
        if total_duration < timedelta(minutes=5):
            await interaction.response.send_message("Minimum mute duration is 5 minutes.", ephemeral=True)
            return
        elif total_duration > timedelta(days=30):
            await interaction.response.send_message("Maximum mute duration is 30 days.", ephemeral=True)
            return

        now = datetime.now().astimezone()
        unmute_time = now + total_duration

        await member.edit(timed_out_until=unmute_time)
        await interaction.response.send_message(f"{member.mention} has been muted for: {reason} (Duration: `{total_duration}`)")

        mutes_data = load_data(MUTES_FILE)
        mutes_data[str(member.id)] = unmute_time.isoformat()
        save_data(MUTES_FILE, mutes_data)
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@tree.command(name="note", description="Add a note to a member")
@app_commands.describe(member="The member to add a note to", note="The note to add")
async def note(interaction: discord.Interaction, member: discord.Member, note: str):
    if interaction.user.guild_permissions.manage_messages:
        notes_data = load_data(NOTES_FILE)
        if str(member.id) not in notes_data:
            notes_data[str(member.id)] = []
        formatted_note = f'{note} - {interaction.user.name}#{interaction.user.discriminator}'
        notes_data[str(member.id)].append(formatted_note)
        save_data(NOTES_FILE, notes_data)
        await interaction.response.send_message(f"Note added to {member.mention}")
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@tree.command(name="notes", description="View notes for a member")
@app_commands.describe(member="The member to view notes for")
async def notes(interaction: discord.Interaction, member: discord.Member):
    notes_data = load_data(NOTES_FILE)
    user_notes = notes_data.get(str(member.id), [])

    if not user_notes:
        await interaction.response.send_message(f"{member.display_name} has no notes.", ephemeral=True)
        return

    embed = discord.Embed(title=f"Notes for {member.display_name}", color=discord.Color.dark_red())
    for i, note in enumerate(user_notes, 1):
        embed.add_field(name=f"Note {i}", value=note, inline=False)

    await interaction.response.send_message(embed=embed)

@tree.command(name="whois", description="Get information about a member")
@app_commands.describe(member="The member to get information about")
async def whois(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.guild_permissions.manage_messages:

        nickname = member.display_name
        username = member.name
        user_id = member.id
        roles = [role.mention for role in member.roles if role != interaction.guild.default_role]

        warnings_data = load_data(WARNINGS_FILE)
        user_warnings = warnings_data.get(str(member.id), [])

        notes_data = load_data(NOTES_FILE)
        user_notes = notes_data.get(str(member.id), [])

        discord_join_date = member.created_at.strftime("%d-%m-%Y")
        server_join_date = member.joined_at.strftime("%d-%m-%Y")

        embed = discord.Embed(
            title=f"Information for {nickname}",
            color=discord.Color.dark_red()
        )
        embed.add_field(name="Username", value=f"**{nickname}** `(@{username})`", inline=False)
        embed.add_field(name="User ID", value=f"```{user_id}```", inline=False)
        embed.add_field(name="Roles", value=", ".join(roles) if roles else "No roles", inline=False)

        if user_warnings:
            embed.add_field(name="Warnings", value="\n".join(user_warnings), inline=False)
        else:
            embed.add_field(name="Warnings", value="No warnings", inline=False)

        if user_notes:
            embed.add_field(name="Notes", value="\n".join(user_notes), inline=False)
        else:
            embed.add_field(name="Notes", value="No notes", inline=False)

        embed.add_field(name="Discord Join Date", value=discord_join_date, inline=True)
        embed.add_field(name="Server Join Date", value=server_join_date, inline=True)

        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@tree.command(name="membercount", description="Get the total number of members in the server")
async def membercount(interaction: discord.Interaction):
    guild = interaction.guild
    if guild:
        total_members = guild.member_count
        embed = discord.Embed(
            title="Member Count",
            description=f"**{total_members}**",
            color=discord.Color.dark_red()
        )
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Could not retrieve the member count.", ephemeral=True)

# @client.event
# async def on_message(message):
#     if message.author.bot:
#         return
#     if any(pattern.search(message.content) for pattern in banned_word_patterns):
#         try:
#             await message.delete()
#             await message.channel.send(f"{message.author.mention}, your message contained banned words and has been deleted.")
#         except discord.Forbidden:
#             logging.error(f"Could not delete message in {message.channel.name} by {message.author.display_name}.")
#         return

@client.event
async def on_raw_reaction_add(payload):
    if payload.emoji.name == STAR_EMOJI:
        channel = client.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        if message.id not in starred_messages:
            reaction = discord.utils.get(message.reactions, emoji=STAR_EMOJI)
            if reaction and reaction.count >= 3:
                starred_messages.add(message.id)
                starboard_channel = client.get_channel(STARBOARD_CHANNEL_ID)

                embed = discord.Embed(description=message.content, color=discord.Color.gold())
                embed.set_author(name=message.author.display_name, icon_url=message.author.avatar.url)
                embed.add_field(name="Jump to message", value=f"[Click here]({message.jump_url})", inline=False)

                if message.attachments:
                    if any(attachment.url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')) for attachment in message.attachments):
                        for attachment in message.attachments:
                            if attachment.url.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                                embed.set_image(url=attachment.url)
                                await starboard_channel.send(embed=embed)
                                return
                    else:
                        await starboard_channel.send(embed=embed)
                        for attachment in message.attachments:
                            await starboard_channel.send(attachment.url)
                        return
                await starboard_channel.send(embed=embed)
@client.event
async def on_member_join(member):
    welcome_channel = client.get_channel(WELCOME_CHANNEL_ID)

    if welcome_channel:
        embed = discord.Embed(
            title=f"Welcome to the server, `{member.name}`!",
            description=f"We are glad to have you here, {member.mention}. Enjoy your stay!",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text=f"Joined on {member.joined_at.strftime('%d-%m-%Y')}")

        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        else:
            embed.set_thumbnail(url=member.default_avatar_url)

        await welcome_channel.send(embed=embed)
    else:
        logging.error("Welcome channel not found. Make sure the channel ID is correct.")

@tree.command(name="serverstatus", description="Get the current status of the server")
async def serverstatus(interaction: discord.Interaction):
    if interaction.user.guild_permissions.manage_messages:
        # count recent errors and warnings
        recent_errors = [log for log in log_capture if 'ERROR' in log][:100]
        recent_warnings = [log for log in log_capture if 'WARNING' in log][:100]

        status = "🟢 All systems operational"
        if recent_errors:
            status = "🔴 There are recent errors"
        elif recent_warnings:
            status = "🟠 There are recent warnings"

        embed = discord.Embed(
            title="Server Status",
            color=discord.Color.green() if status == "🟢 All systems operational" else discord.Color.red() if status == "🔴 There are recent errors" else discord.Color.orange()
        )
        embed.add_field(name="Status", value=status, inline=False)

        if recent_warnings:
            warnings_text = "\n".join(recent_warnings[-5:])
            if len(warnings_text) > 1024:
                warnings_text = warnings_text[:1021] + "..."
            embed.add_field(name="Recent Warnings", value=warnings_text, inline=False)
        else:
            embed.add_field(name="Recent Warnings", value="No recent warnings", inline=False)

        if recent_errors:
            errors_text = "\n".join(recent_errors[-5:])
            if len(errors_text) > 1024:
                errors_text = errors_text[:1021] + "..."
            embed.add_field(name="Recent Errors", value=errors_text, inline=False)
        else:
            embed.add_field(name="Recent Errors", value="No recent errors", inline=False)

        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

token = os.getenv("TOKEN")
client.run(token)
