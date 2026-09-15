import asyncio
import datetime
import os
import discord
from discord.ext import commands, tasks
import scrapetube

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = 1549244979879084033

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

tracked_videos = {}

def check_youtube_video(video_id):
    """التحقق من وجود الفيديو على يوتيوب باستخدام scrapetube"""
    try:
        videos = list(scrapetube.get_videos(video_ids=[video_id]))
        if videos:
            video_data = videos[0]
            title = video_data.get('title', {}).get('runs', [{}])[0].get('text', 'عنوان غير معروف')
            return {'status': 'available', 'title': title}
        return {'status': 'removed', 'reason': 'فيديو محذوف أو غير متاح'}
    except Exception as e:
        return {'status': 'removed', 'reason': str(e)}

def extract_video_id(url):
    """استخراج ID الفيديو من الرابط"""
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    if not check_videos.is_running():
        check_videos.start()

@bot.command(name="track")
async def track(ctx, url: str):
    await ctx.send("🔍 جاري فحص الفيديو وتأكيد الرابط...")
    video_id = extract_video_id(url)
    info = await asyncio.to_thread(check_youtube_video, video_id)
    
    if info['status'] == 'available':
        tracked_videos[video_id] = {'title': info['title'], 'url': url}
        await ctx.send(f"✅ تم بدء مراقبة الفيديو بنجاح:\n**{info['title']}**")
    else:
        await ctx.send(f"❌ تعذر إضافة الفيديو للمراقبة. السبب: `{info.get('reason', 'خطأ غير معروف')}`")

@tasks.loop(minutes=5)
async def check_videos():
    if not tracked_videos:
        return
    
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    for video_id, data in list(tracked_videos.items()):
        info = await asyncio.to_thread(check_youtube_video, video_id)
        if info['status'] == 'removed':
            embed = discord.Embed(
                title="🚨 تنبيه: تم حذف فيديو!",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="عنوان الفيديو", value=data['title'], inline=False)
            embed.add_field(name="الرابط", value=data['url'], inline=False)
            embed.add_field(name="الحالة", value=info['reason'], inline=False)
            
            await channel.send(embed=embed)
            del tracked_videos[video_id]

bot.run(TOKEN)
