import os
import asyncio
import yt_dlp
import requests
import tempfile
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL   = "@joinpremiummodsx"          # your channel username
ADMIN_IDS = []                           # add your Telegram user ID here, e.g. [123456789]

# ─────────────────────────────────────────────
#  IN-MEMORY STORAGE
# ─────────────────────────────────────────────
user_db: dict[int, dict] = {}   # { user_id: {"name": str, "downloads": int} }
pending_urls: dict[int, str] = {}  # { user_id: url } – waiting for format choice


# ═════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════

def track_user(update: Update):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "User"
    if uid not in user_db:
        user_db[uid] = {"name": name, "downloads": 0}

def increment_downloads(user_id: int):
    if user_id in user_db:
        user_db[user_id]["downloads"] += 1

async def is_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m = await context.bot.get_chat_member(CHANNEL, update.effective_user.id)
        return m.status in ["member", "administrator", "creator"]
    except Exception:
        return False

def detect_platform(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:   return "YouTube"
    if "instagram.com" in u:                      return "Instagram"
    if "tiktok.com" in u:                         return "TikTok"
    if "facebook.com" in u or "fb.watch" in u:   return "Facebook"
    if "twitter.com" in u or "x.com" in u:        return "Twitter/X"
    if "pinterest.com" in u or "pin.it" in u:     return "Pinterest"
    if "reddit.com" in u or "redd.it" in u:       return "Reddit"
    if "vimeo.com" in u:                           return "Vimeo"
    if "dailymotion.com" in u:                     return "Dailymotion"
    if "soundcloud.com" in u:                      return "SoundCloud"
    return "Unknown"

PLATFORM_ICONS = {
    "YouTube":     "▶️",
    "Instagram":   "📸",
    "TikTok":      "🎵",
    "Facebook":    "📘",
    "Twitter/X":   "🐦",
    "Pinterest":   "📌",
    "Reddit":      "🤖",
    "Vimeo":       "🎞️",
    "Dailymotion": "📹",
    "SoundCloud":  "🎧",
}

SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be",
    "instagram.com",
    "tiktok.com",
    "facebook.com", "fb.watch",
    "twitter.com", "x.com",
    "pinterest.com", "pin.it",
    "reddit.com", "redd.it",
    "vimeo.com",
    "dailymotion.com",
    "soundcloud.com",
]

JOIN_KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅  Join Channel", url=f"https://t.me/{CHANNEL.lstrip('@')}")],
    [InlineKeyboardButton("🔄  I've Joined!", callback_data="check_join")],
])

async def gate_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Return True if user may proceed; False = gated (message already sent)."""
    if await is_member(update, context):
        return True
    msg = (
        "🔒  *Access Required*\n\n"
        "To use this bot you must join our channel first.\n\n"
        "👇 Tap the button below, then press *I've Joined!*"
    )
    if update.message:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=JOIN_KEYBOARD)
    elif update.callback_query:
        await update.callback_query.message.edit_text(msg, parse_mode="Markdown", reply_markup=JOIN_KEYBOARD)
    return False


# ═════════════════════════════════════════════
#  YT-DLP CORE  (video OR audio)
# ═════════════════════════════════════════════

def _build_ydl_opts(mode: str) -> dict:
    """mode = 'video' | 'audio'"""
    base = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 45,
        "retries": 3,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }
    if mode == "audio":
        base["format"] = "bestaudio/best"
        base["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
        base["outtmpl"] = "%(title).80s.%(ext)s"
    else:
        # Prefer a direct mp4 stream ≤ 50 MB; fall back to best available
        base["format"] = (
            "bestvideo[ext=mp4][filesize<50M]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<50M]/"
            "best[filesize<50M]/best"
        )
        base["merge_output_format"] = "mp4"
        base["outtmpl"] = "%(title).80s.%(ext)s"
    return base


async def extract_info_only(url: str) -> dict:
    """Extract metadata without downloading (fast preview)."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "skip_download": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    }
    loop = asyncio.get_event_loop()
    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    return await loop.run_in_executor(None, _run)


async def download_media(url: str, mode: str, tmpdir: str) -> Path:
    """Download to tmpdir; return path of downloaded file."""
    opts = _build_ydl_opts(mode)
    opts["outtmpl"] = str(Path(tmpdir) / opts["outtmpl"])

    loop = asyncio.get_event_loop()
    downloaded: list[Path] = []

    def _hook(d):
        if d["status"] == "finished":
            downloaded.append(Path(d["filename"]))

    opts["progress_hooks"] = [_hook]

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    await loop.run_in_executor(None, _run)

    if downloaded:
        # For audio the postprocessor renames to .mp3
        base = downloaded[0].with_suffix("")
        for ext in [".mp3", ".m4a", ".webm", ".mp4", ".mkv", ".ogg"]:
            candidate = base.with_suffix(ext)
            if candidate.exists():
                return candidate
        if downloaded[0].exists():
            return downloaded[0]

    # Fallback: find anything in tmpdir
    files = list(Path(tmpdir).iterdir())
    if files:
        return max(files, key=lambda f: f.stat().st_size)

    raise FileNotFoundError("Download produced no file.")


# ═════════════════════════════════════════════
#  COMMAND HANDLERS
# ═════════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    name = update.effective_user.first_name or "there"

    if not await is_member(update, context):
        await gate_check(update, context)
        return

    text = (
        f"✨ *Welcome back, {name}!*\n\n"
        "I can download videos & audio from almost any platform — "
        "fast, clean, and free.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔗 *Just send me a link!*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📦 *Supported Platforms*\n"
        "▶️ YouTube  •  📸 Instagram\n"
        "🎵 TikTok  •  📘 Facebook\n"
        "🐦 Twitter/X  •  📌 Pinterest\n"
        "🤖 Reddit  •  🎞️ Vimeo\n"
        "📹 Dailymotion  •  🎧 SoundCloud\n\n"
        "💡 *Tip:* After sending a link, choose\n"
        "🎬 Video  *or*  🎵 Audio!\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 _Powered by @reelsdownloadersbot_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    text = (
        "📖 *How to use this bot*\n\n"
        "1️⃣  Open any supported app\n"
        "2️⃣  Find the video you want\n"
        "3️⃣  Tap *Share → Copy Link*\n"
        "4️⃣  Paste the link here\n"
        "5️⃣  Choose 🎬 *Video* or 🎵 *Audio*\n"
        "6️⃣  File will be sent directly!\n\n"
        "⚠️ *Make sure the content is public.*\n\n"
        "🆘 Problems? Try sending the link again or check it opens in a browser."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)
    uid = update.effective_user.id
    info = user_db.get(uid, {})
    total_users = len(user_db)
    my_downloads = info.get("downloads", 0)

    text = (
        "📊 *Bot Statistics*\n\n"
        f"👥  Total Users:    *{total_users}*\n"
        f"📥  Your Downloads: *{my_downloads}*\n\n"
        "_Stats reset when bot restarts._"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────
#  JOIN CHECK CALLBACK
# ─────────────────────────────────────────────

async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = update.effective_user.first_name or "there"

    if await is_member(update, context):
        await query.message.edit_text(
            f"🎉 *Welcome, {name}!*\n\n"
            "You're all set! Send me any video link to get started. 🚀",
            parse_mode="Markdown"
        )
    else:
        await query.message.edit_text(
            "❌ *Not joined yet.*\n\n"
            "Please join the channel first, then tap *I've Joined!* again.",
            parse_mode="Markdown",
            reply_markup=JOIN_KEYBOARD
        )


# ─────────────────────────────────────────────
#  FORMAT CHOICE CALLBACK  (video / audio)
# ─────────────────────────────────────────────

async def format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Starting download…")

    uid  = update.effective_user.id
    data = query.data  # "dl_video_<uid>" or "dl_audio_<uid>"

    # Parse callback data
    try:
        parts = data.split("_")
        mode       = parts[1]          # "video" or "audio"
        target_uid = int(parts[2])
    except Exception:
        await query.message.edit_text("⚠️ Invalid request. Please send the link again.")
        return

    if uid != target_uid:
        await query.answer("❌ This button isn't for you.", show_alert=True)
        return

    url = pending_urls.pop(uid, None)
    if not url:
        await query.message.edit_text(
            "⏰ *Session expired.*\n\nPlease send your link again.",
            parse_mode="Markdown"
        )
        return

    platform = detect_platform(url)
    icon     = PLATFORM_ICONS.get(platform, "🌐")
    mode_label = "🎬 Video" if mode == "video" else "🎵 Audio"

    await query.message.edit_text(
        f"⏬ *Downloading {mode_label}…*\n\n"
        f"{icon}  Platform: *{platform}*\n"
        "⏳  Please wait, this may take a moment…",
        parse_mode="Markdown"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            file_path = await download_media(url, mode, tmpdir)
            size_mb   = file_path.stat().st_size / (1024 * 1024)

            # Telegram bot API limit is 50 MB for sendVideo/sendAudio via bot
            if size_mb > 49:
                await query.message.edit_text(
                    f"⚠️ *File too large* ({size_mb:.1f} MB)\n\n"
                    "Telegram bots can only send files up to 49 MB.\n"
                    "Try a shorter video or switch to audio-only.",
                    parse_mode="Markdown"
                )
                return

            increment_downloads(uid)
            caption = (
                f"✅ *{mode_label} ready!*\n\n"
                f"{icon}  *{platform}*\n"
                f"📦  Size: {size_mb:.1f} MB\n\n"
                "_@reelsdownloadersbot_"
            )

            if mode == "audio":
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=open(file_path, "rb"),
                    caption=caption,
                    parse_mode="Markdown",
                )
            else:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=open(file_path, "rb"),
                    caption=caption,
                    parse_mode="Markdown",
                    supports_streaming=True,
                )

            await query.message.delete()

        except Exception as e:
            err_msg = str(e)[:300]
            await query.message.edit_text(
                "❌ *Download Failed*\n\n"
                f"`{err_msg}`\n\n"
                "✅ Make sure the content is *public*\n"
                "✅ Double-check the link is correct\n"
                "✅ Try a different link format",
                parse_mode="Markdown"
            )


# ─────────────────────────────────────────────
#  MAIN MESSAGE HANDLER  (receives URLs)
# ─────────────────────────────────────────────

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    track_user(update)

    if not await gate_check(update, context):
        return

    url = update.message.text.strip()

    if not any(d in url.lower() for d in SUPPORTED_DOMAINS):
        await update.message.reply_text(
            "🔗 *Send a valid video link!*\n\n"
            "Supported:\n"
            "▶️ YouTube  •  📸 Instagram\n"
            "🎵 TikTok  •  📘 Facebook\n"
            "🐦 Twitter/X  •  📌 Pinterest\n"
            "🤖 Reddit  •  🎞️ Vimeo\n"
            "📹 Dailymotion  •  🎧 SoundCloud",
            parse_mode="Markdown"
        )
        return

    uid      = update.effective_user.id
    platform = detect_platform(url)
    icon     = PLATFORM_ICONS.get(platform, "🌐")

    # Show a "fetching info" message
    status_msg = await update.message.reply_text(
        f"🔍 *Fetching info…*\n\n{icon} *{platform}*",
        parse_mode="Markdown"
    )

    try:
        info     = await extract_info_only(url)
        title    = (info.get("title") or "Untitled")[:80]
        duration = info.get("duration") or 0
        uploader = info.get("uploader") or info.get("channel") or ""
        view_str = ""
        if info.get("view_count"):
            vc = info["view_count"]
            view_str = f"👁️  {vc:,} views\n" if vc < 1_000_000 else f"👁️  {vc/1_000_000:.1f}M views\n"
        dur_str = ""
        if duration:
            m, s   = divmod(int(duration), 60)
            h, m   = divmod(m, 60)
            dur_str = f"⏱️  {h}h {m}m {s}s\n" if h else f"⏱️  {m}m {s}s\n"

        # Store URL pending format choice
        pending_urls[uid] = url

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🎬  Video", callback_data=f"dl_video_{uid}"),
            InlineKeyboardButton("🎵  Audio", callback_data=f"dl_audio_{uid}"),
        ]])

        await status_msg.edit_text(
            f"✨ *Found it!*\n\n"
            f"{icon}  *{platform}*\n"
            f"📝  {title}\n"
            + (f"👤  {uploader}\n" if uploader else "")
            + dur_str
            + view_str
            + "\n━━━━━━━━━━━━━━━━━━━━\n"
            "Choose download format 👇",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    except Exception as e:
        err = str(e)[:300]
        await status_msg.edit_text(
            "❌ *Could not fetch info*\n\n"
            f"`{err}`\n\n"
            "Make sure the link is public and correct.",
            parse_mode="Markdown"
        )


# ═════════════════════════════════════════════
#  ENTRY POINT
# ═════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help",  help_cmd))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CallbackQueryHandler(check_join,    pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(format_choice, pattern=r"^dl_(video|audio)_\d+$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("🤖 Bot is running…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
