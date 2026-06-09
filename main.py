import asyncio
import os
import string

import discord
import yt_dlp
from discord.ext import commands


intents = discord.Intents.default()
intents.message_content = True

COMMAND_PREFIX_LETTER = os.getenv("COMMAND_PREFIX_LETTER", "t")
if len(COMMAND_PREFIX_LETTER) != 1 or COMMAND_PREFIX_LETTER not in string.ascii_letters:
    raise RuntimeError("COMMAND_PREFIX_LETTER must be one alphabet letter.")

bot = commands.Bot(command_prefix=f"{COMMAND_PREFIX_LETTER}!", intents=intents)

queues = {}
idle_disconnect_tasks = {}
current_items = {}
loop_items = {}

try:
    MAX_PLAYLIST_ITEMS = int(os.getenv("MAX_PLAYLIST_ITEMS", "100"))
except ValueError as e:
    raise RuntimeError("MAX_PLAYLIST_ITEMS must be an integer.") from e

if MAX_PLAYLIST_ITEMS < 1:
    raise RuntimeError("MAX_PLAYLIST_ITEMS must be 1 or greater.")

STREAM_YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
}

PLAYLIST_YDL_OPTIONS = {
    "extract_flat": "in_playlist",
    "ignoreerrors": True,
    "noplaylist": False,
    "quiet": True,
    "no_warnings": True,
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def cancel_idle_disconnect(guild_id):
    task = idle_disconnect_tasks.pop(guild_id, None)
    if task and not task.done():
        task.cancel()


def normalize_youtube_url(entry):
    url = entry.get("webpage_url") or entry.get("url")
    if not url:
        video_id = entry.get("id")
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
        return None

    if url.startswith("http://") or url.startswith("https://"):
        return url

    return f"https://www.youtube.com/watch?v={url}"


def extract_audio_items(url):
    with yt_dlp.YoutubeDL(PLAYLIST_YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        return [], False

    if "entries" not in info:
        item_url = info.get("webpage_url") or url
        title = info.get("title") or "Unknown title"
        return [{"url": item_url, "title": title}], False

    items = []
    for entry in info.get("entries") or []:
        if not entry:
            continue

        item_url = normalize_youtube_url(entry)
        if not item_url:
            continue

        title = entry.get("title") or "Unknown title"
        items.append({"url": item_url, "title": title})

        if len(items) >= MAX_PLAYLIST_ITEMS:
            break

    return items, True


def extract_stream_url(url):
    with yt_dlp.YoutubeDL(STREAM_YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)
        return info["url"], info.get("title") or "Unknown title"


def schedule_play_next(ctx, error=None):
    if error:
        print(f"Audio player error: {error}")

    bot.loop.call_soon_threadsafe(lambda: bot.loop.create_task(play_next(ctx)))


async def create_audio_source(item):
    stream_url, title = await asyncio.to_thread(extract_stream_url, item["url"])
    source = await discord.FFmpegOpusAudio.from_probe(stream_url, **FFMPEG_OPTIONS)
    item["title"] = title
    return source, title


async def start_item(ctx, item):
    source, title = await create_audio_source(item)
    current_items[ctx.guild.id] = dict(item)
    ctx.voice_client.play(source, after=lambda error: schedule_play_next(ctx, error))
    return title


async def play_next(ctx):
    guild_id = ctx.guild.id
    voice_client = ctx.voice_client

    if not voice_client:
        return

    if loop_items.get(guild_id):
        item = dict(loop_items[guild_id])
    elif queues.get(guild_id):
        item = queues[guild_id].pop(0)
        if item.get("loop"):
            loop_items[guild_id] = dict(item)
    else:
        current_items.pop(guild_id, None)
        cancel_idle_disconnect(guild_id)
        idle_disconnect_tasks[guild_id] = bot.loop.create_task(auto_disconnect(ctx))
        return

    try:
        title = await start_item(ctx, item)
    except Exception as e:
        await ctx.send(f"Failed to prepare next track: {e}")
        if loop_items.get(guild_id):
            loop_items.pop(guild_id, None)
        await play_next(ctx)
        return

    if loop_items.get(guild_id):
        await ctx.send(f"Looping: **{title}**")
    else:
        await ctx.send(f"Now playing: **{title}**")


async def auto_disconnect(ctx):
    await asyncio.sleep(300)

    voice_client = ctx.voice_client
    if voice_client and not voice_client.is_playing() and not voice_client.is_paused():
        current_items.pop(ctx.guild.id, None)
        loop_items.pop(ctx.guild.id, None)
        await voice_client.disconnect()
        await ctx.send("Disconnected after 5 minutes of inactivity.")

    idle_disconnect_tasks.pop(ctx.guild.id, None)


@bot.command(aliases=["p"])
async def play(ctx, url: str):
    if not ctx.author.voice:
        return await ctx.send("Join a voice channel first.")

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    guild_id = ctx.guild.id
    cancel_idle_disconnect(guild_id)

    async with ctx.typing():
        try:
            items, is_playlist = await asyncio.to_thread(extract_audio_items, url)
            if not items:
                return await ctx.send("No playable tracks were found.")

            is_busy = ctx.voice_client.is_playing() or ctx.voice_client.is_paused()

            if is_busy:
                queues.setdefault(guild_id, []).extend(items)
                if is_playlist:
                    await ctx.send(f"Added playlist to queue: {len(items)} tracks.")
                else:
                    await ctx.send(f"Added to queue: **{items[0]['title']}**")
                return

            first_item = items.pop(0)
            title = await start_item(ctx, first_item)

            if items:
                queues.setdefault(guild_id, []).extend(items)
                await ctx.send(
                    f"Now playing: **{title}**\n"
                    f"Added {len(items)} more tracks to queue."
                )
            else:
                await ctx.send(f"Now playing: **{title}**")
        except Exception as e:
            await ctx.send(f"Error: {e}")


@bot.command(aliases=["s"])
async def stop(ctx):
    guild_id = ctx.guild.id
    queues[guild_id] = []
    current_items.pop(guild_id, None)
    loop_items.pop(guild_id, None)
    cancel_idle_disconnect(guild_id)

    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Stopped and disconnected.")
    else:
        await ctx.send("I am not connected to a voice channel.")


@bot.command(aliases=["n"])
async def next(ctx):
    guild_id = ctx.guild.id
    was_looping = guild_id in loop_items
    loop_items.pop(guild_id, None)

    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        ctx.voice_client.stop()
        if was_looping:
            await ctx.send("Loop disabled. Skipping to the next track.")
        else:
            await ctx.send("Skipped.")
    else:
        await ctx.send("Nothing is currently playing.")


@bot.command(name="loop", aliases=["l"])
async def loop_current(ctx):
    guild_id = ctx.guild.id
    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_playing():
        return await ctx.send("Nothing is currently playing.")

    current_item = current_items.get(guild_id)
    if not current_item:
        return await ctx.send("No current track information was found.")

    loop_items[guild_id] = dict(current_item)
    await ctx.send(f"Loop enabled: **{current_item['title']}**")


@bot.command(name="loopplay", aliases=["lp"])
async def loop_play(ctx, url: str):
    if not ctx.author.voice:
        return await ctx.send("Join a voice channel first.")

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    guild_id = ctx.guild.id
    cancel_idle_disconnect(guild_id)

    async with ctx.typing():
        try:
            items, is_playlist = await asyncio.to_thread(extract_audio_items, url)
            if not items:
                return await ctx.send("No playable tracks were found.")

            if is_playlist:
                return await ctx.send("Playlist loop is not supported.")

            item = items[0]

            if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                queues.setdefault(guild_id, []).append({**item, "loop": True})
                await ctx.send(f"Added loop track to queue: **{item['title']}**")
            else:
                loop_items[guild_id] = dict(item)
                title = await start_item(ctx, item)
                await ctx.send(f"Looping: **{title}**")
        except Exception as e:
            await ctx.send(f"Error: {e}")


@bot.command(aliases=["q"])
async def queue(ctx):
    guild_id = ctx.guild.id
    if not queues.get(guild_id):
        return await ctx.send("The queue is empty.")

    msg = "Queue:\n"
    for i, item in enumerate(queues[guild_id][:10], 1):
        loop_label = " (loop)" if item.get("loop") else ""
        msg += f"{i}. {item['title']}{loop_label}\n"
    if len(queues[guild_id]) > 10:
        msg += f"...and {len(queues[guild_id]) - 10} more tracks"
    await ctx.send(msg)


@bot.command(name="delete", aliases=["d", "remove", "rm"])
async def delete_from_queue(ctx, position: int = None):
    guild_id = ctx.guild.id
    queue_items = queues.get(guild_id)

    if position is None:
        return await ctx.send(f"Usage: {COMMAND_PREFIX_LETTER}!d <queue number>")

    if not queue_items:
        return await ctx.send("The queue is empty.")

    if position < 1 or position > len(queue_items):
        return await ctx.send(f"Queue number must be between 1 and {len(queue_items)}.")

    removed = queue_items.pop(position - 1)
    await ctx.send(f"Removed from queue: **{removed['title']}**")


@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel is None:
        return

    voice_client = before.channel.guild.voice_client
    if not voice_client or voice_client.channel != before.channel:
        return

    non_bot_members = [m for m in before.channel.members if not m.bot]
    if not non_bot_members:
        guild_id = before.channel.guild.id
        queues[guild_id] = []
        current_items.pop(guild_id, None)
        loop_items.pop(guild_id, None)
        cancel_idle_disconnect(guild_id)
        await voice_client.disconnect()


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing argument: {error.param.name}")
        return

    if isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument.")
        return

    raise error


token = os.getenv("DISCORD_TOKEN")
if not token:
    raise RuntimeError("DISCORD_TOKEN is not set.")

bot.run(token)
