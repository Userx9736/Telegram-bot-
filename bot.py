import yt_dlp
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
BOT_TOKEN = os.environ.get("BOT_TOKEN")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text

    await update.message.reply_text("Downloading...")

    ydl_opts = {
        'outtmpl': 'video.%(ext)s',
        'quiet': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        await update.message.reply_video(video=open('video.mp4', 'rb'))

    except:
        await update.message.reply_text("Failed to download")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle))

app.run_polling()
