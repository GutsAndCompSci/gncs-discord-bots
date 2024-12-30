import discord
from discord.app_commands import CommandTree
import yt_dlp as youtube_dl
import asyncio
import logging
import os
from discord.ui import Button, View
import math
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.voice_states = True 

activity = discord.Activity(type=discord.ActivityType.listening, name="La Grenadière")
client = discord.Client(intents=intents, activity=activity)
tree = CommandTree(client)

allowed_role_id = 1
booster_role_id = 1

class QueueView(View):
    def __init__(self, songs, current_song, user):
        super().__init__(timeout=60.0)
        self.songs = songs
        self.current_song = current_song
        self.user = user
        self.items_per_page = 10
        self.total_pages = math.ceil(len(songs) / self.items_per_page)
        self.current_page = 0

        self.prev_button = Button(label="⏮️", style=discord.ButtonStyle.success)
        self.next_button = Button(label="⏭️", style=discord.ButtonStyle.success)

        self.prev_button.callback = self.prev_page
        self.next_button.callback = self.next_page

        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.current_page > 0:
            self.add_item(self.prev_button)
        if self.current_page < self.total_pages - 1:
            self.add_item(self.next_button)

    async def update_embed(self, interaction):
        embed = self.generate_embed(self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)

    def generate_embed(self, page):
        embed = discord.Embed(title="Song Queue", description="List of songs in the queue", color=0x808000)
        start = page * self.items_per_page
        end = start + self.items_per_page
        page_songs = self.songs[start:end]

        if self.current_song and page == 0:
            embed.add_field(name="**Currently Playing**", value=self.current_song.title, inline=False)

        for i, song in enumerate(page_songs, start=start + 1):
            embed.add_field(name=f"#{i}", value=song.title, inline=False)

        embed.set_footer(text=f"Page {page + 1}/{self.total_pages}")
        return embed

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("You are not allowed to use these buttons.", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await self.update_embed(interaction)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user != self.user:
            await interaction.response.send_message("You are not allowed to use these buttons.", ephemeral=True)
            return
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            await self.update_embed(interaction)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True, 
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn',
    'executable': 'ffmpeg'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            entries = data['entries']
            playlist = []
            for entry in entries:
                filename = entry['url'] if stream else ytdl.prepare_filename(entry)
                playlist.append(cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=entry))
            return playlist
        else:
            filename = data['url'] if stream else ytdl.prepare_filename(data)
            return [cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)]

def has_allowed_role(interaction, playlist=False):
    if playlist:
        return discord.utils.get(interaction.user.roles, id=booster_role_id) is not None
    else:
        return discord.utils.get(interaction.user.roles, id=allowed_role_id) is not None

class MusicPlayer:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.current = None

    async def play_next(self, voice_client):
        if not self.queue.empty():
            self.current = await self.queue.get()
            voice_client.play(self.current, after=lambda e: self.play_next_after(e, voice_client))
            return True
        return False

    def play_next_after(self, error, voice_client):
        if error:
            logging.error(f'Player error: {error}')
        asyncio.run_coroutine_threadsafe(self.play_next(voice_client), client.loop)

music_player = MusicPlayer()

@client.event
async def on_ready():
    await tree.sync()
    logging.info(f'Logged in as {client.user}!')

@tree.command(name="join", description="Tells the bot to join the voice channel")
async def join(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    if not interaction.user.voice:
        await interaction.response.send_message(f"{interaction.user.name} is not connected to a voice channel", ephemeral=True)
        return

    channel = interaction.user.voice.channel
    try:
        await channel.connect()
        await interaction.response.send_message(f"Joined {channel}")
    except discord.ClientException as e:
        await interaction.response.send_message(f"An error occurred: ```ansi \n{str(e)}```", ephemeral=True)
    except discord.opus.OpusNotLoaded as e:
        await interaction.response.send_message("Opus library is not loaded", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"An error occurred: ```ansi \n{str(e)}```", ephemeral=True)

@tree.command(name="leave", description="To make the bot leave the voice channel")
async def leave(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await interaction.response.send_message("Disconnected from the voice channel")
    else:
        await interaction.response.send_message("The bot is not connected to a voice channel.", ephemeral=True)

@tree.command(name="play", description="Play a song or playlist from a YouTube URL")
async def play(interaction: discord.Interaction, url: str):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    try:
        if not interaction.user.voice:
            await interaction.response.send_message("You are not connected to a voice channel.", ephemeral=True)
            return

        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.response.send_message("Bot is not in a voice channel.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False) 
        playlist = await YTDLSource.from_url(url, loop=client.loop, stream=True)

        for player in playlist:
            await music_player.queue.put(player)

        if not voice_client.is_playing():
            await music_player.play_next(voice_client)
            await interaction.followup.send(f'**Now playing:** `{playlist[0].title}`')
        else:
            queue_position = music_player.queue.qsize()
            await interaction.followup.send(f"Added `{playlist[0].title}` to the queue. Currently at queue position {queue_position}")
    except Exception as e:
        await interaction.followup.send(f'An error occurred: {e}', ephemeral=True)

@tree.command(name="pause", description="Pause the currently playing song")
async def pause(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("Paused the song")
    else:
        await interaction.response.send_message("Currently no audio is playing.", ephemeral=True)

@tree.command(name="resume", description="Resume the currently paused song")
async def resume(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("Resumed the song")
    else:
        await interaction.response.send_message("The audio is not paused.", ephemeral=True)

@tree.command(name="stop", description="Stop the currently playing song")
async def stop(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        voice_client.pause()
        await interaction.response.send_message("Stopped the song")
    else:
        await interaction.response.send_message("Currently no audio is playing.", ephemeral=True)

@tree.command(name="current", description="Show the currently playing song")
async def current(interaction: discord.Interaction):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    current_song = music_player.current

    if not current_song:
        await interaction.response.send_message("No song is currently playing.", ephemeral=True)
        return

    embed = discord.Embed(title="Currently Playing", description=current_song.title, color=0x808000)
    await interaction.response.send_message(embed=embed)

@tree.command(name="queue", description="Show the song queue")
async def queue(interaction: discord.Interaction):

    songs = list(music_player.queue._queue)
    current_song = music_player.current

    if not songs:
        await interaction.response.send_message("The queue is currently empty.", ephemeral=True)
        return

    embed = discord.Embed(title="Song Queue", description="List of songs in the queue", color=0x808000)
    if current_song:
        embed.add_field(name="**Currently Playing**", value=current_song.title, inline=False)

    embed.set_footer(text="Page 1/1")  # Initial placeholder footer

    view = QueueView(songs, current_song, interaction.user)
    await interaction.response.send_message(embed=view.generate_embed(0), view=view)

@tree.command(name="skip", description="Skip the currently playing song")
async def skip(interaction: discord.Interaction, count: int = 1):
    if not has_allowed_role(interaction):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        for _ in range(count):
            voice_client.stop()
            await asyncio.sleep(1) 

        if count == 1:
            await interaction.response.send_message(f"Skipped {count} song")
        else:
            await interaction.response.send_message(f"Skipped {count} songs")
    else:
        await interaction.response.send_message("Currently no audio is playing.", ephemeral=True)
        
client.run(os.getenv("MUSIC_TOKEN"))
