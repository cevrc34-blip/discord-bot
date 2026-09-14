import os
import discord
from discord.ext import commands

# معرف القناة المحددة للتنبيهات
CHANNEL_ID = 1548939865293586492
TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'تم تسجيل الدخول بنجاح باسم: {bot.user}')
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send("🤖 البوت يعمل الان وجاهز لمراقبة الروابط 24/7!")

@bot.event
async def on_message(message):
    # تجاهل رسائل البوت نفسه
    if message.author == bot.user:
        return

    # التفاعل عند إرسال رابط فيديو في القناة
    if "youtube.com" in message.content or "youtu.be" in message.content:
        await message.channel.send(f"🔍 تم رصد رابط فيديو بواسطة {message.author.mention}، جاري معالجته...")

    await bot.process_commands(message)

if __name__ == "__main__":
    bot.run(TOKEN)
