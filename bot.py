from __future__ import annotations
import os
import asyncio
import logging
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes,
)
from telegram.constants import ParseMode
import yt_dlp

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
BOT_TAG        = os.environ.get("BOT_TAG", "@reelsdownloadersbot")
ADMIN_IDS_RAW  = os.environ.get("ADMIN_IDS", "")
ADMIN_IDS      = set(int(x) for x in ADMIN_IDS_RAW.split(",") if x.strip().isdigit())

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE    = MAX_FILE_SIZE_MB * 1024 * 1024
DOWNLOAD_TIMEOUT = 300

user_stats    = {}
pending_urls  = {}
bot_start_time = datetime.now()

# ═══════════════════════════════════════════════════════════════
#  PLATFORM DATA
# ═══════════════════════════════════════════════════════════════

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
    "twitch.tv", "clips.twitch.tv",
    "linkedin.com",
    "tumblr.com",
    "bilibili.com",
    "streamable.com",
]

PLATFORM_ICONS = {
    "youtube":     "🎬 YouTube",
    "instagram":   "📸 Instagram",
    "tiktok":      "🎵 TikTok",
    "facebook":    "📘 Facebook",
    "twitter":     "🐦 Twitter / X",
    "pinterest":   "📌 Pinterest",
    "reddit":      "🤖 Reddit",
    "vimeo":       "🎥 Vimeo",
    "dailymotion": "🎬 Dailymotion",
    "soundcloud":  "🎧 SoundCloud",
    "twitch":      "💜 Twitch",
    "linkedin":    "💼 LinkedIn",
    "tumblr":      "🌀 Tumblr",
    "bilibili":    "📺 Bilibili",
    "streamable":  "▶️ Streamable",
}


def detect_platform(url):
    u = url.lower()
    if "youtube.com"     in u or "youtu.be"    in u: return "youtube"
    if "instagram.com"   in u:                        return "instagram"
    if "tiktok.com"      in u:                        return "tiktok"
    if "facebook.com"    in u or "fb.watch"    in u: return "facebook"
    if "twitter.com"     in u or "x.com"       in u: return "twitter"
    if "pinterest.com"   in u or "pin.it"      in u: return "pinterest"
    if "reddit.com"      in u or "redd.it"     in u: return "reddit"
    if "vimeo.com"       in u:                        return "vimeo"
    if "dailymotion.com" in u:                        return "dailymotion"
    if "soundcloud.com"  in u:                        return "soundcloud"
    if "twitch.tv"       in u:                        return "twitch"
    if "linkedin.com"    in u:                        return "linkedin"
    if "tumblr.com"      in u:                        return "tumblr"
    if "bilibili.com"    in u:                        return "bilibili"
    if "streamable.com"  in u:                        return "streamable"
    return "unknown"


def fmt_duration(secs):
    if not secs: return ""
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


def fmt_number(n):
    if not n: return "0"
    n = int(n)
    if n >= 1_000_000_000: return f"{n/1_000_000_000:.1f}B"
    if n >= 1_000_000:     return f"{n/1_000_000:.1f}M"
    if n >= 1_000:         return f"{n/1_000:.1f}K"
    return str(n)


def fmt_size(b):
    if not b: return ""
    b = int(b)
    if b >= 1_073_741_824: return f"{b/1_073_741_824:.1f} GB"
    if b >= 1_048_576:     return f"{b/1_048_576:.1f} MB"
    if b >= 1_024:         return f"{b/1_024:.1f} KB"
    return f"{b} B"


def fmt_uptime():
    delta = datetime.now() - bot_start_time
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s   = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s"


def esc(text):
    for ch in ("*", "_", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


def friendly_error(msg):
    m = msg.lower()
    if "private"       in m: return "🔒 This content is *private*."
    if "login"         in m or "sign in" in m: return "🔐 Login required."
    if "not available" in m: return "🌍 Not available in server region."
    if "removed"       in m or "deleted" in m: return "🗑️ Content removed."
    if "copyright"     in m: return "©️ Blocked by copyright."
    if "rate"          in m: return "🚦 Rate limited — wait and retry."
    return f"`{msg[:200]}`"

# ═══════════════════════════════════════════════════════════════
#  YT-DLP
# ═══════════════════════════════════════════════════════════════

def base_opts():
    return {
        "quiet":        True,
        "no_warnings":  True,
        "noplaylist":   True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        },
    }


async def get_media_info(url):
    opts = {**base_opts(), "skip_download": True}
    loop = asyncio.get_event_loop()
    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    return await loop.run_in_executor(None, _run)


async def download_media(url, media_type, tmp_dir):
    loop    = asyncio.get_event_loop()
    outtmpl = os.path.join(tmp_dir, "%(title).80s.%(ext)s")

    if media_type == "audio":
        opts = {
            **base_opts(),
            "format":     "bestaudio/best",
            "outtmpl":    outtmpl,
            "postprocessors": [{
                "key":              "FFmpegExtractAudio",
                "preferredcodec":   "mp3",
                "preferredquality": "192",
            }],
        }
    else:
        opts = {
            **base_opts(),
            "format": (
                "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                "/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
                "/best[height<=1080]/best"
            ),
            "outtmpl":             outtmpl,
            "merge_output_format": "mp4",
            "max_filesize":        MAX_FILE_SIZE,
        }

    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    try:
        await asyncio.wait_for(
            loop.run_in_executor(None, _run),
            timeout=DOWNLOAD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return None, "⏱️ Download timed out. File may be too large."
    except yt_dlp.utils.DownloadError as e:
        return None, friendly_error(str(e))
    except Exception as e:
        return None, f"❌ Error: {str(e)[:200]}"

    files = [f for f in Path(tmp_dir).iterdir() if f.is_file()]
    if not files:
        return None, "❌ No file saved. Please try again."

    filepath = str(max(files, key=lambda p: p.stat().st_size))
    size     = os.path.getsize(filepath)

    if size > MAX_FILE_SIZE:
        os.remove(filepath)
        return None, (
            f"📦 File too large ({fmt_size(size)}).\n"
            f"Max is {MAX_FILE_SIZE_MB} MB.\n"
            "Try 🎵 Audio format instead."
        )
    return filepath, ""


def register(user):
    uid = user.id
    if uid not in user_stats:
        user_stats[uid] = {
            "name":      user.first_name or "User",
            "username":  user.username or "",
            "downloads": 0,
            "joined":    datetime.now(),
        }

# ═══════════════════════════════════════════════════════════════
#  TEXT BUILDERS
# ═══════════════════════════════════════════════════════════════

def start_text(name):
    return (
        "╔══════════════════════════════════════╗\n"
        "║    📥  MEDIA  DOWNLOADER  BOT  📥    ║\n"
        "║         Premium Edition  ✨           ║\n"
        "╚══════════════════════════════════════╝\n\n"
        f"✨ *Welcome, {esc(name)}!*\n\n"
        "Send me any video or audio link and I will\n"
        "*download & send the file directly* here!\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📱 *Supported Platforms*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎬 YouTube      📸 Instagram     🎵 TikTok\n"
        "📘 Facebook     🐦 Twitter/X     📌 Pinterest\n"
        "🤖 Reddit       🎥 Vimeo         🎧 SoundCloud\n"
        "💜 Twitch       🎬 Dailymotion   📺 Bilibili\n"
        "💼 LinkedIn     🌀 Tumblr        ▶️ Streamable\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *How to Use*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "1️⃣  Copy any video link\n"
        "2️⃣  Paste the link here\n"
        "3️⃣  Choose 🎬 *Video* or 🎵 *Audio*\n"
        "4️⃣  Receive your file directly ✅\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔰 *Commands*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "/start  — Welcome screen\n"
        "/help   — Help guide\n"
        "/stats  — Your statistics\n"
        "/about  — About this bot\n\n"
        f"_{BOT_TAG}_"
    )


HELP_TEXT = (
    "📖 *HELP GUIDE*\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📥 *How to Download*\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "1. Copy any video link\n"
    "2. Paste it here\n"
    "3. Choose 🎬 Video or 🎵 Audio\n"
    "4. File sent directly in chat ✅\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "📦 *Limits*\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "• Max file size: *50 MB*\n"
    "• Video: up to *1080p MP4*\n"
    "• Audio: *MP3 192 kbps*\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ *Common Errors*\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    "🔒 Private content — cannot download\n"
    "📦 Too large — use Audio format\n"
    "🌍 Region blocked — not available\n"
    "🚦 Rate limited — wait and retry\n\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
)


def about_text():
    return (
        "ℹ️ *ABOUT THIS BOT*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🤖 *Media Downloader Bot* — Premium Edition\n\n"
        "Download from *15+ platforms* directly\n"
        "inside Telegram. No browser, no pop-ups.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚙️ *Tech Stack*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• python-telegram-bot 20.3\n"
        "• yt-dlp (latest)\n"
        "• FFmpeg (audio conversion)\n\n"
        f"_{BOT_TAG}_"
    )


def stats_text(uid):
    data  = user_stats.get(uid, {"name": "User", "downloads": 0, "joined": datetime.now(), "username": ""})
    total = sum(v.get("downloads", 0) for v in user_stats.values())
    return (
        "📊 *YOUR STATISTICS*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 *User:*        {esc(data.get('name','User'))}\n"
        f"🔖 *Username:*   @{esc(data.get('username','') or 'N/A')}\n"
        f"📥 *Downloads:*  {data.get('downloads', 0)}\n"
        f"📅 *Joined:*     {data.get('joined', datetime.now()).strftime('%d %b %Y')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 *Total Users:*     {len(user_stats)}\n"
        f"📦 *Total Downloads:* {total}\n"
        f"⏱️ *Bot Uptime:*      {fmt_uptime()}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"_{BOT_TAG}_"
    )


def start_kb():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Help",    callback_data="cb_help"),
            InlineKeyboardButton("📊 Stats",   callback_data="cb_stats"),
        ],
        [InlineKeyboardButton("ℹ️ About",      callback_data="cb_about")],
    ])


def back_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Back", callback_data="cb_start"),
    ]])

# ═══════════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register(user)
    await update.message.reply_text(
        start_text(user.first_name or "User"),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=start_kb(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register(update.effective_user)
    await update.message.reply_text(
        HELP_TEXT + f"_{BOT_TAG}_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_kb(),
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register(user)
    await update.message.reply_text(
        stats_text(user.id),
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register(update.effective_user)
    await update.message.reply_text(
        about_text(),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=back_kb(),
    )


async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return
    msg = " ".join(context.args)
    if not msg:
        await update.message.reply_text("Usage: /broadcast Your message")
        return
    sent = failed = 0
    for target_uid in list(user_stats.keys()):
        try:
            await context.bot.send_message(
                chat_id=target_uid,
                text=f"📢 *Announcement*\n\n{msg}",
                parse_mode=ParseMode.MARKDOWN,
            )
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await update.message.reply_text(f"✅ Sent: {sent} | ❌ Failed: {failed}")

# ═══════════════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    register(user)
    uid  = user.id
    url  = update.message.text.strip()

    if not any(d in url.lower() for d in SUPPORTED_DOMAINS):
        await update.message.reply_text(
            "❌ *Unsupported Link*\n\n"
            "Supported: YouTube, Instagram, TikTok, Facebook,\n"
            "Twitter/X, Pinterest, Reddit, Vimeo, SoundCloud,\n"
            "Twitch, Dailymotion, Bilibili and more.\n\n"
            f"_{BOT_TAG}_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    platform = detect_platform(url)
    icon     = PLATFORM_ICONS.get(platform, "🌐 Media")

    msg = await update.message.reply_text(
        f"🔍 *Fetching info...*\n\n"
        f"🎯 Platform: *{icon}*\n"
        "⏳ Please wait...",
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        info = await get_media_info(url)
    except Exception as e:
        await msg.edit_text(
            f"❌ *Could not fetch media info*\n\n"
            f"{friendly_error(str(e))}\n\n"
            f"_{BOT_TAG}_",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    pending_urls[uid] = url

    title       = (info.get("title") or "Untitled")[:70]
    uploader    = info.get("uploader") or info.get("channel") or ""
    duration    = info.get("duration", 0)
    views       = info.get("view_count", 0)
    likes       = info.get("like_count", 0)
    upload_date = info.get("upload_date", "")
    if upload_date and len(upload_date) == 8:
        try:
            upload_date = datetime.strptime(upload_date, "%Y%m%d").strftime("%d %b %Y")
        except Exception:
            upload_date = ""

    lines = [
        f"🎯 *{icon}*\n",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📝 *{esc(title)}*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if uploader:    lines.append(f"👤 *Uploader:*  {esc(uploader)}")
    if duration:    lines.append(f"⏱️ *Duration:*  {fmt_duration(duration)}")
    if views:       lines.append(f"👁️ *Views:*     {fmt_number(views)}")
    if likes:       lines.append(f"❤️ *Likes:*     {fmt_number(likes)}")
    if upload_date: lines.append(f"📅 *Uploaded:*  {upload_date}")
    lines += [
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📥 *Select download format:*",
        f"\n_{BOT_TAG}_",
    ]

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Video (MP4)", callback_data=f"video_{uid}"),
            InlineKeyboardButton("🎵 Audio (MP3)", callback_data=f"audio_{uid}"),
        ],
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{uid}")],
    ])

    await msg.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )

# ═══════════════════════════════════════════════════════════════
#  CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid  = update.effective_user.id
    data = query.data

    if data == "cb_start":
        register(update.effective_user)
        name = update.effective_user.first_name or "User"
        await query.edit_message_text(
            start_text(name),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=start_kb(),
        )
        return

    if data == "cb_help":
        await query.edit_message_text(
            HELP_TEXT + f"_{BOT_TAG}_",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_kb(),
        )
        return

    if data == "cb_stats":
        register(update.effective_user)
        await query.edit_message_text(
            stats_text(uid),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_kb(),
        )
        return

    if data == "cb_about":
        await query.edit_message_text(
            about_text(),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_kb(),
        )
        return

    if data.startswith("cancel_"):
        try:
            owner = int(data.split("_", 1)[1])
        except ValueError:
            return
        if owner != uid:
            await query.answer("Not your session!", show_alert=True)
            return
        pending_urls.pop(uid, None)
        await query.edit_message_text(
            "✅ *Cancelled.* Send a new link anytime!",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    try:
        media_type, owner_str = data.rsplit("_", 1)
        owner = int(owner_str)
    except (ValueError, AttributeError):
        return

    if owner != uid:
        await query.answer("Not your session!", show_alert=True)
        return

    if media_type not in ("video", "audio"):
        return

    url = pending_urls.get(uid)
    if not url:
        await query.edit_message_text(
            "⏰ *Session expired.* Please send your link again.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    platform  = detect_platform(url)
    icon      = PLATFORM_ICONS.get(platform, "🌐 Media")
    fmt_label = "Video 🎬" if media_type == "video" else "Audio 🎵"

    await query.edit_message_text(
        f"⬇️ *Downloading {fmt_label}...*\n\n"
        f"🎯 Platform: *{icon}*\n"
        "⏳ This may take a moment...\n\n"
        f"_{BOT_TAG}_",
        parse_mode=ParseMode.MARKDOWN,
    )

    tmp_dir = tempfile.mkdtemp(prefix="tgdl_")
    try:
        filepath, error = await download_media(url, media_type, tmp_dir)

        if error or not filepath:
            await query.edit_message_text(
                f"❌ *Download Failed*\n\n{error}\n\n_{BOT_TAG}_",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        user_stats[uid]["downloads"] = user_stats[uid].get("downloads", 0) + 1
        pending_urls.pop(uid, None)

        size     = os.path.getsize(filepath)
        filename = os.path.basename(filepath)

        await query.edit_message_text(
            f"📤 *Uploading to Telegram...*\n\n"
            f"📁 `{filename}`\n"
            f"📦 {fmt_size(size)}\n\n"
            "⏳ Almost done...",
            parse_mode=ParseMode.MARKDOWN,
        )

        caption = (
            f"✅ *{fmt_label} — Done!*\n\n"
            f"📁 `{esc(filename)}`\n"
            f"📦 *{fmt_size(size)}*\n"
            f"🎯 {icon}\n\n"
            f"_{BOT_TAG}_"
        )

        chat_id = update.effective_chat.id

        with open(filepath, "rb") as fh:
            if media_type == "audio":
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=fh,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                )
            else:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=fh,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                )

        try:
            await query.delete_message()
        except Exception:
            pass

        log.info(f"Sent {media_type} ({fmt_size(size)}) to user {uid}")

    except Exception as e:
        log.exception(f"Error for user {uid}")
        await query.edit_message_text(
            f"❌ *Error*\n\n`{str(e)[:300]}`\n\n_{BOT_TAG}_",
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("Exception:", exc_info=context.error)

# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        log.critical("BOT_TOKEN not set!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("about",     cmd_about))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))

    app.add_handler(CallbackQueryHandler(
        handle_callback,
        pattern=r"^(video|audio|cancel)_\d+$",
    ))
    app.add_handler(CallbackQueryHandler(
        handle_callback,
        pattern=r"^cb_(start|help|stats|about)$",
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message,
    ))

    app.add_error_handler(error_handler)

    log.info("Bot started!")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
