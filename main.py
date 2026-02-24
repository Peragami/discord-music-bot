import discord
from discord.ext import commands
import yt_dlp
import os
import asyncio

# インテントの設定 (メッセージ内容の読み取りが必要)
intents = discord.Intents.default()
intents.message_content = True

# プレフィックスを "t!" に設定
bot = commands.Bot(command_prefix="t!", intents=intents)

# yt-dlpとFFmpegのオプション
YDL_OPTIONS = {'format': 'bestaudio/best', 'noplaylist': 'True'}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# aliases=['p'] を追加することで t!p でも反応するようになります
@bot.command(aliases=['p'])
async def play(ctx, url: str):
    # ユーザーがボイチャにいるか確認
    if not ctx.author.voice:
        return await ctx.send("先にボイスチャンネルに入ってください。")

    # ボットが接続していなければ接続
    if not ctx.voice_client:
        await ctx.author.voice.channel.connect()
    
    async with ctx.typing():
        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                url2 = info['url']
                # FFmpegで再生
                source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
                
                if ctx.voice_client.is_playing():
                    ctx.voice_client.stop()
                
                ctx.voice_client.play(source)
                await ctx.send(f"🎵 再生中: **{info['title']}**")
        except Exception as e:
            await ctx.send(f"エラーが発生しました: {e}")

# 停止コマンド (t!s) もあると便利です
@bot.command(aliases=['s'])
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("バイバイ！")

bot.run(os.getenv('DISCORD_TOKEN'))
