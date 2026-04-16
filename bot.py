import os
import asyncio
import yt_dlp
import tempfile
import time
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing")

# ─────────────────────────────
# GET INFO
# ─────────────────────────────
async def get_info(url):
    loop = asyncio.get_event_loop()

    def run():
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            return ydl.extract_info(url, download=False)

    return await loop.run_in_executor(None, run)

# ─────────────────────────────
# DOWNLOAD WITH PROGRESS
# ─────────────────────────────
async def download_with_progress(url, mode, message, context, chat_id):

    loop = asyncio.get_event_loop()
    start_time = time.time()

    def progress_hook(d):
        if d["status"] == "downloading":
            try:
                percent = d.get("_percent_str", "0%").strip()
                speed = d.get("_speed_str", "0 KB/s")
                eta = d.get("_eta_str", "0s")

                text = (
                    f"⏬ Downloading...\n\n"
                    f"📊 {percent}\n"
                    f"⚡ Speed: {speed}\n"
                    f"⏳ ETA: {eta}"
                )

                asyncio.run_coroutine_threadsafe(
                    message.edit_text(text),
                    loop
                )
            except:
                pass

    def run():
        opts = {
            "format": "bestaudio" if mode == "audio" else "best[ext=mp4]/best",
            "quiet": True,
            "noplaylist": True,
            "progress_hooks": [progress_hook],
        }

        if mode == "audio":
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        with tempfile.TemporaryDirectory() as tmp:
            opts["outtmpl"] = f"{tmp}/%(title).80s.%(ext)s"

            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])

            files = list(Path(tmp).iterdir())
            return files[0]

    file_path = await loop.run_in_executor(None, run)

    total_time = time.time() - start_time

    return file_path, total_time

# ─────────────────────────────
# START
# ─────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send link\n\n🎬 Video\n🎵 Audio\n⚡ Fast Download"
    )

# ─────────────────────────────
# HANDLE LINK
# ─────────────────────────────
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    msg = await update.message.reply_text("🔍 Fetching...")

    try:
        info = await get_info(url)

        title = info.get("title", "Video")[:80]
        thumb = info.get("thumbnail")

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬 Video", callback_data=f"video|{url}"),
            InlineKeyboardButton("🎵 Audio", callback_data=f"audio|{url}")
        ]])

        if thumb:
            await context.bot.send_photo(
                chat_id=update.message.chat_id,
                photo=thumb,
                caption=f"{title}\n\nChoose 👇",
                reply_markup=keyboard
            )
            await msg.delete()
        else:
            await msg.edit_text(title, reply_markup=keyboard)

    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:200]}")

# ─────────────────────────────
# BUTTON CLICK
# ─────────────────────────────
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        mode, url = query.data.split("|", 1)
    except:
        await query.message.edit_text("❌ Invalid request")
        return

    msg = await query.message.edit_text("⏬ Starting...")

    try:
        file, total_time = await download_with_progress(
            url, mode, msg, context, query.message.chat_id
        )

        size = file.stat().st_size / (1024 * 1024)

        caption = (
            f"✅ Done!\n\n"
            f"📦 Size: {size:.1f} MB\n"
            f"⏱ Time: {int(total_time)} sec"
        )

        if mode == "audio":
            await context.bot.send_audio(
                chat_id=query.message.chat_id,
                audio=open(file, "rb"),
                caption=caption
            )
        else:
            await context.bot.send_video(
                chat_id=query.message.chat_id,
                video=open(file, "rb"),
                caption=caption,
                supports_streaming=True
            )

        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Failed: {str(e)[:200]}")

# ─────────────────────────────
# MAIN
# ─────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(CallbackQueryHandler(button, pattern="^(video|audio)\\|"))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
