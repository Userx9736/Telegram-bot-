# ================= PART 1 START =================

import os
import asyncio
import logging
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode
import yt_dlp

# CONFIG
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MAX_FILE_SIZE = 50 * 1024 * 1024
DOWNLOAD_TIMEOUT = 300

user_data_store = {}

# BASE OPTS (PRO)
def _base_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 3,
        "fragment_retries": 3,
    }

# INFO
async def get_media_info(url):
    loop = asyncio.get_running_loop()

    def run():
        with yt_dlp.YoutubeDL(_base_opts()) as ydl:
            return ydl.extract_info(url, download=False)

    return await asyncio.wait_for(loop.run_in_executor(None, run), timeout=60)

# DOWNLOAD (PRO FIXED)
async def download_media(url, media_type, tmp):
    loop = asyncio.get_running_loop()

    if media_type == "audio":
        opts = {
            **_base_opts(),
            "format": "bestaudio/best",
            "outtmpl": f"{tmp}/%(title)s.%(ext)s",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }],
        }
    else:
        opts = {
            **_base_opts(),
            "format": "best[ext=mp4]/best",
            "outtmpl": f"{tmp}/%(title)s.%(ext)s",
        }

    def run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    for i in range(2):
        try:
            await asyncio.wait_for(loop.run_in_executor(None, run), timeout=DOWNLOAD_TIMEOUT)
            break
        except Exception as e:
            if i == 1:
                return None, str(e)

    files = list(Path(tmp).glob("*"))

    if not files:
        return None, "❌ Download failed. Platform blocked or invalid."

    valid = [f for f in files if f.suffix.lower() in [".mp4", ".mp3", ".webm", ".mkv"]]

    if not valid:
        return None, "❌ No valid media file found."

    file = max(valid, key=lambda x: x.stat().st_size)

    if file.stat().st_size > MAX_FILE_SIZE:
        return None, "❌ File too large (50MB limit)."

    return str(file), None

# UI TEXT
def start_text(name):
    return f"""
✨ *Welcome {name}*

📥 Send any video link
🎬 Download Video
🎵 Download Audio

⚡ Fast • Clean • Premium
"""

# COMMANDS
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        start_text(name),
        parse_mode=ParseMode.MARKDOWN
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 Send link → Choose format → Get file"
    )

# MESSAGE
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_data_store[update.effective_user.id] = url

    keyboard = [
        [
            InlineKeyboardButton("🎬 Video", callback_data="video"),
            InlineKeyboardButton("🎵 Audio", callback_data="audio"),
        ]
    ]

    await update.message.reply_text(
        "⚡ Choose format:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
# ================= PART 2 START =================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = update.effective_user.id
    url = user_data_store.get(uid)

    if not url:
        await query.edit_message_text("❌ Send link again")
        return

    media_type = query.data

    await query.edit_message_text("⬇️ Downloading...")

    tmp = tempfile.mkdtemp()

    try:
        file, err = await download_media(url, media_type, tmp)

        if err:
            await query.edit_message_text(err)
            return

        await query.edit_message_text("📤 Uploading...")

        with open(file, "rb") as f:
            if media_type == "audio":
                await context.bot.send_audio(update.effective_chat.id, f)
            else:
                await context.bot.send_video(update.effective_chat.id, f)

        await query.delete_message()

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

# MAIN
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN missing")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    app.run_polling()

if __name__ == "__main__":
    main()

# ================= PART 2 END =================
