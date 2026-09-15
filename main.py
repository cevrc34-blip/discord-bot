import asyncio
import datetime
import os
import discord
from discord.ext import commands, tasks
import yt_dlp

# إعدادات البوت الآمنة
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = 1549244979879084033

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="/", intents=intents)

tracked_videos = {}

def get_video_info(url):
    """جلب معلومات الفيديو باستخدام yt-dlp مع خيارات التمويه لتجاوز الحظر"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'http_headers': {
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                'status': 'available',
                'title': info.get('title', 'عنوان غير معروف'),
                'uploader': info.get('uploader', 'قناة غير معروفة')
            }
        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)
            if "Video unavailable" in error_msg or "Private video" in error_msg:
                return {'status': 'removed', 'reason': 'فيديو محذوف أو خاص'}
            return {'status': 'error', 'reason': error_msg}
        except Exception as e:
            return {'status': 'error', 'reason': str(e)}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    if not check_videos.is_running():
        check_videos.start()

@bot.command(name="track")
async def track(ctx, url: str):
    """إضافة فيديو لقائمة المراقبة"""
    await ctx.send("🔍 جاري فحص الفيديو وتأكيد الرابط...")
    info = await asyncio.to_thread(get_video_info, url)
    
    if info['status'] == 'available':
        tracked_videos[url] = info['title']
        await ctx.send(f"✅ تم بدء مراقبة الفيديو بنجاح:\n**{info['title']}**")
    else:
        await ctx.send(f"❌ تعذر إضافة الفيديو للمراقبة. السبب: `{info.get('reason', 'خطأ غير معروف')}`")

@tasks.loop(minutes=5)
async def check_videos():
    """فحص دوري للفيديوهات المراقبة كل 5 دقائق"""
    if not tracked_videos:
        return
    
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    for url, title in list(tracked_videos.items()):
        info = await asyncio.to_thread(get_video_info, url)
        if info['status'] == 'removed':
            embed = discord.Embed(
                title="🚨 تنبيه: تم حذف فيديو!",
                color=discord.Color.red(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.add_field(name="عنوان الفيديو", value=title, inline=False)
            embed.add_field(name="الرابط", value=url, inline=False)
            embed.add_field(name="الحالة", value=info['reason'], inline=False)
            
            await channel.send(embed=embed)
            del tracked_videos[url]

bot.run(TOKEN)
