import os
import yt_dlp
import asyncio
import tempfile
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing")

# ───────────── HANDLE MESSAGE ─────────────
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎬 Video", callback_data=f"video|{url}"),
        InlineKeyboardButton("🎵 Audio", callback_data=f"audio|{url}")
    ]])

    await update.message.reply_text("Choose format:", reply_markup=keyboard)

# ───────────── DOWNLOAD ─────────────
async def download(url, mode):
    loop = asyncio.get_event_loop()

    def run():
        opts = {
            "format": "bestaudio" if mode == "audio" else "best",
            "quiet": True
        }

        if mode == "audio":
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3"
            }]

        with tempfile.TemporaryDirectory() as tmp:
            opts["outtmpl"] = f"{tmp}/%(title).%(ext)s"

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            return list(Path(tmp).iterdir())[0]

    return await loop.run_in_executor(None, run)

# ───────────── BUTTON ─────────────
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode, url = query.data.split("|")

    msg = await query.message.edit_text("Downloading...")

    try:
        file = await download(url, mode)

        if mode == "audio":
            await context.bot.send_audio(query.message.chat_id, audio=open(file, "rb"))
        else:
            await context.bot.send_video(query.message.chat_id, video=open(file, "rb"))

        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"Error: {str(e)}")

# ───────────── MAIN ─────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(CallbackQueryHandler(button, pattern="^(video|audio)\\|"))

    app.run_polling()

if __name__ == "__main__":
    main()
