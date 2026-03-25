import os
import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")

user_set = set()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_set.add(update.effective_user.id)
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 Welcome {name}!\n\n"
        "🤖 Premium Video Downloader Bot!\n\n"
        "📥 Send me any link:\n"
        "▶️ YouTube\n"
        "📘 Facebook\n\n"
        "I will send you the direct download link!\n\n"
        "⚡ Powered by Premium Bot"
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_set.add(update.effective_user.id)
    url = update.message.text

    await update.message.reply_text("🔍 Getting download link... Please wait!")

    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = info.get('url') or info['formats'][-1]['url']
            title = info.get('title', 'Video')
            duration = info.get('duration', 0)
            minutes = duration // 60
            seconds = duration % 60

        await update.message.reply_text(
            f"✅ Found!\n\n"
            f"🎬 Title: {title}\n"
            f"⏱ Duration: {minutes}m {seconds}s\n\n"
            f"📥 Download Link:\n{video_url}\n\n"
            f"👆 Click the link to download!"
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Error: {str(e)}\n\n"
            "Please make sure:\n"
            "✅ Link is public\n"
            "✅ Link is correct\n"
            "✅ Not an Instagram link"
        )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Total Users: {len(user_set)}")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()