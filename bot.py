import os
import re
import sqlite3
from datetime import datetime, timezone

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "5"))
DATABASE = os.getenv("DATABASE", "bot.db")

if not DISCORD_TOKEN or not YOUTUBE_API_KEY:
    raise RuntimeError("Missing DISCORD_TOKEN or YOUTUBE_API_KEY in environment variables.")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

db = sqlite3.connect(DATABASE, check_same_thread=False)
db.row_factory = sqlite3.Row

db.executescript("""
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL UNIQUE,
    channel_id TEXT NOT NULL,
    title TEXT NOT NULL,
    channel_title TEXT NOT NULL,
    discord_channel_id INTEGER NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_views INTEGER DEFAULT 0,
    last_likes INTEGER DEFAULT 0,
    last_comments INTEGER DEFAULT 0,
    last_subscribers INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    removed_notified INTEGER DEFAULT 0
);
""")
db.commit()

YOUTUBE_URL_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{6,})"
)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def parse_video_id(url: str):
    match = YOUTUBE_URL_RE.search(url)
    return match.group(1) if match else None

def format_num(number: int):
    return f"{number:,}"

def format_duration(start_iso: str):
    start = datetime.fromisoformat(start_iso)
    seconds = max(0, int((datetime.now(timezone.utc) - start).total_seconds()))
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    if days:
        return f"{days}d {hours}h {minutes}m {seconds}s"
    return f"{hours}h {minutes}m {seconds}s"

async def yt_get(session, endpoint, params):
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
    async with session.get(url, params=params, timeout=30) as response:
        data = await response.json()
        if response.status != 200:
            message = data.get("error", {}).get("message", f"YouTube HTTP {response.status}")
            raise RuntimeError(message)
        return data

async def get_video(session, video_id):
    data = await yt_get(session, "videos", {
        "part": "snippet,statistics,status",
        "id": video_id,
        "key": YOUTUBE_API_KEY,
    })
    return data["items"][0] if data.get("items") else None

async def get_channel_subscribers(session, channel_id):
    data = await yt_get(session, "channels", {
        "part": "statistics",
        "id": channel_id,
        "key": YOUTUBE_API_KEY,
    })
    if not data.get("items"):
        return 0
    return int(data["items"][0]["statistics"].get("subscriberCount", 0))

async def send_removed_alert(row):
    channel = bot.get_channel(row["discord_channel_id"])

    if channel is None:
        try:
            channel = await bot.fetch_channel(row["discord_channel_id"])
        except Exception as error:
            print("Could not find Discord channel:", error)
            return

    embed = discord.Embed(
        title="🚫 Video Removed / Unavailable",
        description=f"**{row['title']}**\nby **{row['channel_title']}**",
        color=discord.Color.red(),
    )

    embed.add_field(
        name="Original Link",
        value=f"https://www.youtube.com/watch?v={row['video_id']}",
        inline=False,
    )

    embed.add_field(
        name="📊 Last Known Stats",
        value=(
            f"📺 Views: {format_num(row['last_views'])}\n"
            f"👍 Likes: {format_num(row['last_likes'])}\n"
            f"💬 Comments: {format_num(row['last_comments'])}\n"
            f"👥 Subscribers: {format_num(row['last_subscribers'])}"
        ),
        inline=False,
    )

    embed.add_field(
        name="⏱️ Removed in",
        value=format_duration(row["first_seen"]),
        inline=False,
    )

    embed.set_footer(
        text=f"Detected at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    await channel.send(content="🚨 **Video Removed!**", embed=embed)

async def check_all_videos():
    rows = db.execute(
        "SELECT * FROM watches WHERE removed_notified = 0"
    ).fetchall()

    if not rows:
        return

    async with aiohttp.ClientSession() as session:
        # YouTube allows multiple video IDs in one videos.list request.
        for start in range(0, len(rows), 50):
            batch = rows[start:start + 50]
            ids = ",".join(row["video_id"] for row in batch)

            try:
                data = await yt_get(session, "videos", {
                    "part": "snippet,statistics,status",
                    "id": ids,
                    "key": YOUTUBE_API_KEY,
                })
            except Exception as error:
                print("YouTube request error:", error)
                continue

            returned = {item["id"]: item for item in data.get("items", [])}

            for row in batch:
                item = returned.get(row["video_id"])

                if item:
                    statistics = item.get("statistics", {})
                    title = item.get("snippet", {}).get("title", row["title"])
                    channel_title = item.get(
                        "snippet", {}
                    ).get("channelTitle", row["channel_title"])

                    views = int(statistics.get("viewCount", 0))
                    likes = int(statistics.get("likeCount", 0))
                    comments = int(statistics.get("commentCount", 0))

                    db.execute("""
                        UPDATE watches
                        SET title=?, channel_title=?, last_seen=?,
                            last_views=?, last_likes=?, last_comments=?,
                            failure_count=0
                        WHERE video_id=?
                    """, (
                        title,
                        channel_title,
                        now_iso(),
                        views,
                        likes,
                        comments,
                        row["video_id"],
                    ))

                else:
                    # Require two consecutive failed checks before alerting.
                    # This helps reduce false removal alerts.
                    failures = row["failure_count"] + 1

                    if failures >= 2:
                        db.execute("""
                            UPDATE watches
                            SET failure_count=?, removed_notified=1
                            WHERE video_id=?
                        """, (failures, row["video_id"]))

                        db.commit()

                        fresh = db.execute(
                            "SELECT * FROM watches WHERE video_id=?",
                            (row["video_id"],)
                        ).fetchone()

                        try:
                            await send_removed_alert(fresh)
                        except Exception as error:
                            print("Discord alert error:", error)
                    else:
                        db.execute("""
                            UPDATE watches
                            SET failure_count=?
                            WHERE video_id=?
                        """, (failures, row["video_id"]))

            db.commit()

@tasks.loop(minutes=CHECK_INTERVAL_MINUTES)
async def monitor_loop():
    await check_all_videos()

@monitor_loop.before_loop
async def before_monitor():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
    except Exception as error:
        print("Slash command sync error:", error)

    if not monitor_loop.is_running():
        monitor_loop.start()

    print(
        f"Logged in as {bot.user}. "
        f"Monitoring every {CHECK_INTERVAL_MINUTES} minutes."
    )

@bot.tree.command(
    name="watch",
    description="Start monitoring a YouTube video for removal"
)
@app_commands.describe(url="The YouTube video URL to monitor")
async def watch(interaction: discord.Interaction, url: str):
    video_id = parse_video_id(url)

    if not video_id:
        await interaction.response.send_message(
            "❌ Invalid YouTube video URL.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)

    async with aiohttp.ClientSession() as session:
        try:
            item = await get_video(session, video_id)

            if not item:
                await interaction.followup.send(
                    "❌ The video does not exist or is currently unavailable.",
                    ephemeral=True,
                )
                return

            channel_id = item["snippet"]["channelId"]
            subscribers = await get_channel_subscribers(session, channel_id)

        except Exception as error:
            await interaction.followup.send(
                f"❌ Error: {error}",
                ephemeral=True,
            )
            return

    statistics = item.get("statistics", {})

    try:
        db.execute("""
            INSERT INTO watches
            (
                video_id, channel_id, title, channel_title,
                discord_channel_id, first_seen, last_seen,
                last_views, last_likes, last_comments,
                last_subscribers
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            video_id,
            channel_id,
            item["snippet"]["title"],
            item["snippet"]["channelTitle"],
            interaction.channel_id,
            now_iso(),
            now_iso(),
            int(statistics.get("viewCount", 0)),
            int(statistics.get("likeCount", 0)),
            int(statistics.get("commentCount", 0)),
            subscribers,
        ))
        db.commit()

    except sqlite3.IntegrityError:
        await interaction.followup.send(
            "⚠️ This video is already being monitored.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        f"✅ **Video added to monitoring.**\n"
        f"📺 **{item['snippet']['title']}**\n"
        f"⏱️ The video will be checked every **{CHECK_INTERVAL_MINUTES} minutes**.",
        ephemeral=True,
    )

@bot.tree.command(
    name="unwatch",
    description="Stop monitoring a YouTube video"
)
@app_commands.describe(url="The YouTube video URL")
async def unwatch(interaction: discord.Interaction, url: str):
    video_id = parse_video_id(url)

    if not video_id:
        await interaction.response.send_message(
            "❌ Invalid YouTube URL.",
            ephemeral=True,
        )
        return

    cursor = db.execute(
        "DELETE FROM watches WHERE video_id=?",
        (video_id,)
    )
    db.commit()

    if cursor.rowcount:
        message = "✅ Monitoring stopped for this video."
    else:
        message = "⚠️ This video is not being monitored."

    await interaction.response.send_message(
        message,
        ephemeral=True,
    )

@bot.tree.command(
    name="list",
    description="Show the YouTube videos currently being monitored"
)
async def list_watches(interaction: discord.Interaction):
    rows = db.execute("""
        SELECT title, video_id
        FROM watches
        WHERE discord_channel_id=? AND removed_notified=0
    """, (interaction.channel_id,)).fetchall()

    if not rows:
        await interaction.response.send_message(
            "There are no videos being monitored in this channel.",
            ephemeral=True,
        )
        return

    text = "\n".join(
        f"• {row['title']} — `{row['video_id']}`"
        for row in rows[:50]
    )

    await interaction.response.send_message(
        f"**Monitored videos ({len(rows)}):**\n{text}",
        ephemeral=True,
    )

bot.run(DISCORD_TOKEN)
