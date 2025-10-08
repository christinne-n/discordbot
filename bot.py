import os
import asyncio
import discord
from discord.ext import commands
import yt_dlp

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="$", intents=intents)

YDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch1",  # allow search terms, picks top result
}
FFMPEG_OPTS = {"options": "-vn"}  # audio only

# Simple in-memory queues per guild
queues: dict[int, asyncio.Queue] = {}
now_playing: dict[int, str] = {}

def get_queue(guild_id: int) -> asyncio.Queue:
    if guild_id not in queues:
        queues[guild_id] = asyncio.Queue()
    return queues[guild_id]

async def ensure_connected(ctx: commands.Context) -> discord.VoiceClient | None:
    if ctx.author.voice is None:
        await ctx.send("Please join a voice channel first! >:O")
        return None
    voice = ctx.voice_client
    if voice is None:
        voice = await ctx.author.voice.channel.connect()
    return voice

async def play_next(ctx: commands.Context):
    """Internal: pulls next track from queue and plays it."""
    q = get_queue(ctx.guild.id)
    if q.empty():
        now_playing.pop(ctx.guild.id, None)
        return

    entry = await q.get()  # (title, url, webpage_url)
    title, stream_url, page_url = entry
    now_playing[ctx.guild.id] = title

    # Create source and play
    src = await discord.FFmpegOpusAudio.from_probe(stream_url, **FFMPEG_OPTS)
    vc = ctx.voice_client
    if not vc:
        return
    def after(err):
        if err:
            print("Player error:", err)
        # Schedule next song on the bot loop
        fut = asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        try:
            fut.result()
        except Exception as e:
            print("after() error:", e)

    vc.play(src, after=after)
    await ctx.send(f"▶️ Now playing: **{title}**\n{page_url}")

def resolve_query(query: str):
    """Use yt-dlp to get a playable audio URL + nice title."""
    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(query, download=False)
        if "entries" in info:  # search results
            info = info["entries"][0]
        stream_url = info["url"]
        title = info.get("title", "audio")
        page_url = info.get("webpage_url") or query
        return title, stream_url, page_url

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")

@bot.command()
async def hello(ctx):
    await ctx.send("Hello :O) !")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if bot.user and bot.user.mentioned_in(message):
        await message.channel.send(f"Hi {message.author.mention}, I am here! >:3")
    await bot.process_commands(message)

@bot.command()
async def join(ctx):
    voice = await ensure_connected(ctx)
    if voice:
        await ctx.send(f"Joined {voice.channel.mention}")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        queues.pop(ctx.guild.id, None)
        now_playing.pop(ctx.guild.id, None)
        await ctx.send("Left the channel and cleared the queue! :)")
    else:
        await ctx.send("I’m not in a voice channel! >:U")

@bot.command()
async def play(ctx, *, query: str):
    """Play a YouTube URL or search terms.
    NOTE: Spotify links aren’t playable directly. Paste the song title, or I’ll try to search by your text.
    """
    # If someone pasted a Spotify link, explain the workaround
    if "open.spotify.com" in query:
        await ctx.send("Oh no! Spotify links can’t be streamed. :( Please paste the song name (e.g., `$play artist - title`) or a YouTube link.")
        return

    voice = await ensure_connected(ctx)
    if not voice:
        return

    try:
        title, stream_url, page_url = resolve_query(query)
    except Exception as e:
        await ctx.send(f"Couldn’t load that: `{e}` >:(")
        return

    q = get_queue(ctx.guild.id)
    await q.put((title, stream_url, page_url))
    if not voice.is_playing() and not voice.is_paused():
        await play_next(ctx)
    else:
        await ctx.send(f"Queued: **{title}** :D")

@bot.command()
async def skip(ctx):
    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        ctx.voice_client.stop()
        await ctx.send("Skipped! :O")
    else:
        await ctx.send("Nothing is playing...? :/")

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        ctx.voice_client.stop()
        # clear the queue
        q = get_queue(ctx.guild.id)
        while not q.empty():
            q.get_nowait()
        await ctx.send("Stopped and cleared the queue! :)")
    else:
        await ctx.send("I'm not in a voice channel. :(")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Paused! :O")
    else:
        await ctx.send("Nothing is playing?! >:/")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Resumed! :3")
    else:
        await ctx.send("Nothing to resume...? :P")

@bot.command(aliases=["np"])
async def nowplaying(ctx):
    title = now_playing.get(ctx.guild.id)
    await ctx.send(f"Now playing: **{title}**" if title else "Nothing is playing!! >:O")
    
bot.run('#bot-token-here') #removed for security purposes
