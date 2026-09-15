import asyncio
import datetime
import discord
from discord.ext import commands, tasks
import yt_dlp

# إعدادات البوت جاهزة بالكامل
TOKEN = "MTU0ODg0MDQ4ODE1MTQxNjg4Mw.GsBFVD.v7POZj8ibVP0-gUgrrwPsw1X0RxhkK8CiADvA0"
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
                "subs": f"{info.get('channel_follower_count', 0):,}",
                "views": f"{info.get('view_count', 0):,}",
                "likes": f"{info.get('like_count', 0):,}",
                "comments": f"{info.get('comment_count', 0):,}",
                "url": url,
            }
        except Exception:
            return None


@bot.event
async def on_ready():
    print(f"Bot Online: {bot.user.name}")
    check_videos_status.start()


@bot.tree.command(
    name="trackvideo", description="Start tracking a YouTube video"
)
async def trackvideo(interaction: discord.Interaction, url: str):
    await interaction.response.defer()

    info = get_video_info(url)
    if not info:
        await interaction.followup.send(
            "❌ Failed to fetch video. Invalid link or video already removed."
        )
        return

    video_id = info["id"]
    tracked_videos[video_id] = {
        **info,
        "start_time": datetime.datetime.now(datetime.timezone.utc),
    }

    # نص البدء الأبيض بالإنجليزية
    msg_text = (
        f"⏱️ Tracking **{info['title']}**\n"
        f"📹 Channel: {info['channel']}\n"
        f"👥 Subscribers: {info['subs']}"
    )
    await interaction.followup.send(msg_text)


@tasks.loop(seconds=3)
async def check_videos_status():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel or not tracked_videos:
        return

    to_remove = []

    for video_id, data in list(tracked_videos.items()):
        current_info = get_video_info(data["url"])

        # إذا تم حذف الفيديو
        if current_info is None:
            now = datetime.datetime.now(datetime.timezone.utc)
            duration = now - data["start_time"]

            hours, remainder = divmod(int(duration.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = f"{hours}h {minutes}m {seconds}s"

            # كارت الحذف الأحمر المطابق للصورة الأولى
            embed = discord.Embed(
                title="🚨 Video Removed!", color=discord.Color.red()
            )

            embed.description = (
                f"🚫 **Video Removed / Unavailable**\n\n"
                f"**{data['title']}**\n"
                f"by **{data['channel']}**\n\n"
                f"[Original Link]({data['url']})\n\n"
                f"📊 **Last Known Stats**\n"
                f"📺 Views: {data['views']}\n"
                f"👍 Likes: {data['likes']}\n"
                f"💬 Comments: {data['comments']}\n"
                f"👥 Subscribers: {data['subs']}\n"
                f"📹 Channel\n{data['channel']}\n\n"
                f"⏱️ **Removed in**\n{time_str}\n\n"
                f"Detected at {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )

            await channel.send(embed=embed)
            to_remove.append(video_id)

    for vid in to_remove:
        if vid in tracked_videos:
            del tracked_videos[vid]


bot.run(TOKEN)
