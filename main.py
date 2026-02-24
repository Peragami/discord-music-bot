import discord
from discord.ext import commands
import yt_dlp
import os
import asyncio

# インテント設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="t!", intents=intents)

# サーバーごとの再生待ちリスト
queues = {}

# yt-dlp設定
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': 'True',
    'quiet': True,
    'no_warnings': True,
}

# FFmpeg設定
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

def check_queue(ctx):
    """再生終了時に呼ばれる次曲再生ロジック"""
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        # 次の曲の情報を取り出す
        next_data = queues[guild_id].pop(0)
        source = next_data['source']
        title = next_data['title']
        
        ctx.voice_client.play(source, after=lambda e: check_queue(ctx))
        # 非同期でメッセージを送るためにloopを使用
        bot.loop.create_task(ctx.send(f"次の曲を再生します: **{title}**"))
    else:
        # キューが空になったら自動退出のタイマーを開始
        bot.loop.create_task(auto_disconnect(ctx))

async def auto_disconnect(ctx):
    """5分間何もしなければ退出"""
    await asyncio.sleep(300)
    if ctx.voice_client and not ctx.voice_client.is_playing():
        await ctx.voice_client.disconnect()
        await ctx.send("長時間再生がなかったため、退出しました。")

@bot.command(aliases=['p'])
async def play(ctx, url: str):
    """再生・キュー追加"""
    if not ctx.author.voice:
        return await ctx.send("ボイスチャンネルに入ってください。")

    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()

    async with ctx.typing():
        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info['url']
                title = info['title']
                source = await discord.FFmpegOpusAudio.from_probe(stream_url, **FFMPEG_OPTIONS)

                guild_id = ctx.guild.id
                if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                    if guild_id not in queues:
                        queues[guild_id] = []
                    queues[guild_id].append({'source': source, 'title': title})
                    await ctx.send(f"キューに追加しました: **{title}**")
                else:
                    ctx.voice_client.play(source, after=lambda e: check_queue(ctx))
                    await ctx.send(f"🎵 再生開始: **{title}**")
        except Exception as e:
            await ctx.send(f"エラー: {e}")

@bot.command(aliases=['s'])
async def stop(ctx):
    """完全に停止してキューを削除し、退出する"""
    guild_id = ctx.guild.id
    if guild_id in queues:
        queues[guild_id] = [] # キューを空にする
    
    if ctx.voice_client:
        # disconnectすると再生も止まるため、stop()を呼ばずにそのまま抜ける
        await ctx.voice_client.disconnect()
        await ctx.send("バイバイ！")

@bot.command(aliases=['n'])
async def next(ctx):
    """今の曲を飛ばして次の曲へ"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop() # stopを呼ぶと after=check_queue が実行される
        await ctx.send("スキップ！")

@bot.command(aliases=['q'])
async def queue(ctx):
    """現在の待機リストを表示"""
    guild_id = ctx.guild.id
    if guild_id not in queues or not queues[guild_id]:
        return await ctx.send("現在のキューは空です。")
    
    msg = "【待機リスト】\n"
    for i, item in enumerate(queues[guild_id][:10], 1):
        msg += f"{i}. {item['title']}\n"
    if len(queues[guild_id]) > 10:
        msg += f"...他 {len(queues[guild_id]) - 10} 曲"
    await ctx.send(msg)

@bot.event
async def on_voice_state_update(member, before, after):
    """ボイスチャンネルに誰もいなくなったら即時退出"""
    if before.channel is not None and len(before.channel.members) == 1:
        if before.channel.guild.voice_client:
            await before.channel.guild.voice_client.disconnect()

bot.run(os.getenv('DISCORD_TOKEN'))
