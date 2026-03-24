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
        "🤖 I am a Premium Video Downloader Bot!\n\n"
        "📥 I can download from:\n"
        "▶️ YouTube (Video & Audio)\n"
        "📸 Instagram\n"
        "📘 Facebook\n\n"
        "Simply send me any link and I'll download it for you!\n\n"
        "⚡ Powered by Premium Bot"
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_set.add(update.effective_user.id)
    url = update.message.text

    # Audio download
    if "/audio" in url:
        url = url.replace("/audio", "").strip()
        await update.message.reply_text("🎵 Downloading audio... Please wait!")
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': 'audio.%(ext)s',
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
            }],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            await update.message.reply_audio(audio=open('audio.mp3', 'rb'))
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        return

    # Video download
    await update.message.reply_text("⬇️ Downloading video... Please wait!")
    ydl_opts = {
        'format': 'best',
        'outtmpl': 'video.%(ext)s',
        'quiet': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        await update.message.reply_text("📤 Uploading... Almost done!")
        await update.message.reply_video(video=open('video.mp4', 'rb'))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}\n\nMake sure the link is valid!")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Total Users: {len(user_set)}")

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()
