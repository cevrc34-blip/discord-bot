import asyncio
import datetime
import os
import discord
from discord.ext import commands, tasks
import yt_dlp

# إعدادات البوت الآمنة
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = 1549244979879084033

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

tracked_videos = {}

def get_video_info(url):
    """جلب معلومات الفيديو باستخدام yt-dlp"""
    ydl_opts = {"quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                "id": info.get("id"),
                "title": info.get("title"),
                "channel": info.get("uploader"),
                "uploader_url": info.get("uploader_url"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "status": "Available"
            }
        except Exception as e:
            return {"status": "Unavailable", "error": str(e)}

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    check_videos.start()

@bot.command()
async def track(ctx, url: str):
    """أمر إضافة فيديو للمراقبة"""
    if url in tracked_videos:
        await ctx.send("This video is already being tracked!")
        return

    await ctx.send("Analyzing video...")
    info = await asyncio.to_thread(get_video_info, url)

    if info["status"] == "Available":
        tracked_videos[url] = info
        await ctx.send(f"Successfully started tracking: **{info['title']}**")
    else:
        await ctx.send(f"Failed to track video: {info.get('error')}")

@tasks.loop(minutes=5)
async def check_videos():
    """فحص الفيديوهات كل 5 دقائق"""
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    for url, data in list(tracked_videos.items()):
        current_info = await asyncio.to_thread(get_video_info, url)

        if current_info["status"] == "Unavailable":
            embed = discord.Embed(
                title="🚨 Tracked Video Removed/Unavailable!",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Video Title", value=data.get("title", "Unknown"), inline=False)
            embed.add_field(name="Channel", value=data.get("channel", "Unknown"), inline=True)
            embed.add_field(name="URL", value=url, inline=False)
            embed.set_footer(text="Video Monitoring System")

            await channel.send(embed=embed)
            del tracked_videos[url]

if __name__ == "__main__":
    bot.run(TOKEN)
