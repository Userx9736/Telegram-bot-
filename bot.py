import os
import asyncio
import yt_dlp
import tempfile
import subprocess
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set!")

pending = {}

# ─────────────────────────────
# YTDLP OPTIONS
# ─────────────────────────────
def ydl_opts(mode):
    if mode == "audio":
        return {
            "format": "bestaudio",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
            "noplaylist": True,
        }
    else:
        return {
            "format": "best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "quiet": True,
            "noplaylist": True,
        }

# ─────────────────────────────
# GET VIDEO INFO
# ─────────────────────────────
async def get_info(url):
    loop = asyncio.get_event_loop()

    def run():
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            return ydl.extract_info(url, download=False)

    return await loop.run_in_executor(None, run)

# ─────────────────────────────
# DOWNLOAD FILE
# ─────────────────────────────
async def download(url, mode, path):
    opts = ydl_opts(mode)
    opts["outtmpl"] = str(path / "%(title).80s.%(ext)s")

    loop = asyncio.get_event_loop()
    files = []

    def hook(d):
        if d["status"] == "finished":
            files.append(d["filename"])

    opts["progress_hooks"] = [hook]

    def run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    await loop.run_in_executor(None, run)

    if files:
        return Path(files[0])
    raise Exception("Download failed")

# ─────────────────────────────
# COMPRESS VIDEO (>50MB)
# ─────────────────────────────
def compress(input_file):
    output = input_file.with_name("compressed.mp4")

    cmd = [
        "ffmpeg", "-i", str(input_file),
        "-vcodec", "libx264", "-crf", "28",
        "-preset", "fast",
        "-acodec", "aac",
        str(output)
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output if output.exists() else input_file

# ─────────────────────────────
# START COMMAND
# ─────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me any video link!\n\n"
        "I'll give you:\n"
        "🎬 Video\n"
        "🎵 Audio (MP3)\n\n"
        "Fast ⚡ Simple ✅"
    )

# ─────────────────────────────
# HANDLE LINK
# ─────────────────────────────
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.effective_user.id

    msg = await update.message.reply_text("🔍 Fetching info...")

    try:
        info = await get_info(url)

        title = info.get("title", "Video")[:80]
        thumb = info.get("thumbnail")

        pending[uid] = url

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 Video", callback_data=f"video_{uid}"),
            InlineKeyboardButton("🎵 Audio", callback_data=f"audio_{uid}")
        ]])

        if thumb:
            await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=thumb,
                caption=f"🎬 {title}\n\nChoose format 👇",
                reply_markup=keyboard
            )
            await msg.delete()
        else:
            await msg.edit_text(f"{title}\n\nChoose format 👇", reply_markup=keyboard)

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:200]}")

# ─────────────────────────────
# BUTTON CLICK
# ─────────────────────────────
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = update.effective_user.id
    mode = query.data.split("_")[0]

    if uid != int(query.data.split("_")[1]):
        await query.answer("Not your request", show_alert=True)
        return

    url = pending.get(uid)

    if not url:
        await query.message.edit_text("Session expired")
        return

    await query.message.edit_text("⏬ Downloading...")

    with tempfile.TemporaryDirectory() as tmp:
        try:
            file = await download(url, mode, Path(tmp))

            size = file.stat().st_size / (1024 * 1024)

            if size > 49 and mode == "video":
                file = compress(file)
                size = file.stat().st_size / (1024 * 1024)

            if mode == "audio":
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=open(file, "rb"),
                    caption="🎵 Audio Ready"
                )
            else:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=open(file, "rb"),
                    caption=f"🎬 Video Ready ({size:.1f} MB)",
                    supports_streaming=True
                )

            await query.message.delete()

        except Exception as e:
            await query.message.edit_text(f"❌ Failed: {str(e)[:200]}")

# ─────────────────────────────
# MAIN
# ─────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(CallbackQueryHandler(button))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
