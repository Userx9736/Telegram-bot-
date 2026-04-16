import os
import asyncio
import yt_dlp
import tempfile
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set")

# ─────────────────────────────
# Handle incoming link
# ─────────────────────────────
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()

    if not url.startswith("http"):
        await update.message.reply_text("Send a valid link.")
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎬 Video", callback_data=f"video|{url}"),
        InlineKeyboardButton("🎵 Audio", callback_data=f"audio|{url}")
    ]])

    await update.message.reply_text("Choose format:", reply_markup=keyboard)

# ─────────────────────────────
# Download worker
# ─────────────────────────────
async def do_download(url: str, mode: str) -> Path:
    loop = asyncio.get_event_loop()

    def run():
        opts = {
            "quiet": True,
            "noplaylist": True,
            "format": "bestaudio" if mode == "audio" else "best[ext=mp4]/best",
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
            if not files:
                raise RuntimeError("No file produced")
            return files[0]

    return await loop.run_in_executor(None, run)

# ─────────────────────────────
# Button click
# ─────────────────────────────
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        mode, url = query.data.split("|", 1)
    except Exception:
        await query.message.edit_text("Invalid request")
        return

    msg = await query.message.edit_text("⏬ Downloading...")

    try:
        file_path = await do_download(url, mode)

        if mode == "audio":
            await context.bot.send_audio(
                chat_id=query.message.chat_id,
                audio=open(file_path, "rb"),
                caption="🎵 Audio ready"
            )
        else:
            await context.bot.send_video(
                chat_id=query.message.chat_id,
                video=open(file_path, "rb"),
                caption="🎬 Video ready",
                supports_streaming=True
            )

        await msg.delete()

    except Exception as e:
        await msg.edit_text(f"❌ Failed: {str(e)[:200]}")

# ─────────────────────────────
# Main
# ─────────────────────────────
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(CallbackQueryHandler(button, pattern=r"^(video|audio)\|"))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
