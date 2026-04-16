# ════════════════════════════════════════════════════════════
#  MEDIA DOWNLOADER BOT  —  Professional Edition
#  Supports: YouTube · Instagram · TikTok · Facebook ·
#            Twitter/X · Pinterest · Reddit · Vimeo ·
#            Dailymotion · SoundCloud
# ════════════════════════════════════════════════════════════

import os
import asyncio
import tempfile
import logging
import instaloader
import yt_dlp
from pathlib import Path
from datetime import datetime

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL   = "@joinpremiummodsx"          # change to your channel
BOT_TAG   = "@reelsdownloadersbot"       # change to your bot username

# ── Instaloader instance ──────────────────────────────────────
_IL = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    save_metadata=False,
    quiet=True,
)

# ── In-memory stores ──────────────────────────────────────────
# user_db  : { uid: {"name": str, "downloads": int, "joined": str} }
# url_store: { uid: url }  — pending format selection
user_db:   dict[int, dict] = {}
url_store: dict[int, str]  = {}


# ════════════════════════════════════════════════════════════
#  CONSTANTS & MAPPINGS
# ════════════════════════════════════════════════════════════

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

PLATFORM_MAP = {
    ("youtube.com", "youtu.be"):        ("YouTube",     "YT"),
    ("instagram.com",):                 ("Instagram",   "IG"),
    ("tiktok.com",):                    ("TikTok",      "TK"),
    ("facebook.com", "fb.watch"):       ("Facebook",    "FB"),
    ("twitter.com", "x.com"):          ("Twitter / X", "TW"),
    ("pinterest.com", "pin.it"):        ("Pinterest",   "PT"),
    ("reddit.com", "redd.it"):          ("Reddit",      "RD"),
    ("vimeo.com",):                     ("Vimeo",       "VM"),
    ("dailymotion.com",):               ("Dailymotion", "DM"),
    ("soundcloud.com",):                ("SoundCloud",  "SC"),
}

def detect_platform(url: str) -> str:
    u = url.lower()
    for domains, (name, _) in PLATFORM_MAP.items():
        if any(d in u for d in domains):
            return name
    return "Unknown"

# Professional minimal icons (no excess emoji spam)
PLATFORM_ICON = {
    "YouTube":     "◈ YouTube",
    "Instagram":   "◈ Instagram",
    "TikTok":      "◈ TikTok",
    "Twitter / X": "◈ Twitter / X",
    "Facebook":    "◈ Facebook",
    "Pinterest":   "◈ Pinterest",
    "Reddit":      "◈ Reddit",
    "Vimeo":       "◈ Vimeo",
    "Dailymotion": "◈ Dailymotion",
    "SoundCloud":  "◈ SoundCloud",
}

JOIN_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("Join Channel", url=f"https://t.me/{CHANNEL.lstrip('@')}")],
    [InlineKeyboardButton("✓  I've Joined", callback_data="check_join")],
])

def fmt_duration(seconds: int) -> str:
    if not seconds:
        return ""
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"

def fmt_views(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


# ════════════════════════════════════════════════════════════
#  GATE  (channel membership check)
# ════════════════════════════════════════════════════════════

async def is_member(uid: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m = await context.bot.get_chat_member(CHANNEL, uid)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return False

async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    if await is_member(uid, context):
        return True
    text = (
        "┌─  Access Restricted  ─────────────────\n"
        "│\n"
        "│  You must join our channel to use\n"
        "│  this service.\n"
        "│\n"
        "└───────────────────────────────────────"
    )
    target = update.message or update.callback_query.message
    method = target.reply_text if update.message else target.edit_text
    await method(text, reply_markup=JOIN_KB)
    return False


# ════════════════════════════════════════════════════════════
#  USER TRACKING
# ════════════════════════════════════════════════════════════

def register(update: Update):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "User"
    if uid not in user_db:
        user_db[uid] = {
            "name":      name,
            "downloads": 0,
            "joined":    datetime.now().strftime("%d %b %Y"),
        }

def add_download(uid: int):
    if uid in user_db:
        user_db[uid]["downloads"] += 1


# ════════════════════════════════════════════════════════════
#  YT-DLP  —  info extraction & download
# ════════════════════════════════════════════════════════════

_YDL_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}

_YDL_BASE = {
    "quiet":          True,
    "no_warnings":    True,
    "socket_timeout": 40,
    "retries":        4,
    "http_headers":   _YDL_HEADERS,
}


async def ydl_info(url: str) -> dict:
    opts = {**_YDL_BASE, "skip_download": True}
    loop = asyncio.get_event_loop()
    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    return await loop.run_in_executor(None, _run)


def _ydl_download_opts(mode: str, outdir: str) -> dict:
    opts = {
        **_YDL_BASE,
        "outtmpl": str(Path(outdir) / "%(title).60s.%(ext)s"),
    }
    if mode == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key":             "FFmpegExtractAudio",
            "preferredcodec":  "mp3",
            "preferredquality": "192",
        }]
    else:
        opts["format"] = (
            "bestvideo[ext=mp4][filesize<49M]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<49M]/"
            "best[filesize<49M]/best"
        )
        opts["merge_output_format"] = "mp4"
    return opts


async def ydl_download(url: str, mode: str, outdir: str) -> Path:
    opts = _ydl_download_opts(mode, outdir)
    found: list[Path] = []

    def _hook(d):
        if d["status"] == "finished":
            found.append(Path(d["filename"]))

    opts["progress_hooks"] = [_hook]

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).download([url]))

    # Resolve final filename (postprocessor may rename .webm → .mp3)
    for p in found:
        stem = p.with_suffix("")
        for ext in (".mp3", ".m4a", ".mp4", ".mkv", ".webm", ".ogg"):
            c = stem.with_suffix(ext)
            if c.exists():
                return c
        if p.exists():
            return p

    # Last resort: largest file in dir
    files = sorted(Path(outdir).iterdir(), key=lambda f: f.stat().st_size, reverse=True)
    if files:
        return files[0]
    raise FileNotFoundError("yt-dlp produced no output file.")


# ════════════════════════════════════════════════════════════
#  INSTAGRAM  —  instaloader (direct URL, no cookies)
# ════════════════════════════════════════════════════════════

async def ig_fetch(url: str) -> dict:
    """Return metadata dict for an IG reel or post."""
    if "/reel/" in url:
        sc = url.split("/reel/")[1].split("/")[0].split("?")[0]
    elif "/p/" in url:
        sc = url.split("/p/")[1].split("/")[0].split("?")[0]
    else:
        raise ValueError("Send a reel or post link  (e.g. instagram.com/reel/…)")

    loop = asyncio.get_event_loop()
    post = await loop.run_in_executor(
        None, lambda: instaloader.Post.from_shortcode(_IL.context, sc)
    )
    return {
        "title":     (post.caption or "")[:72].strip() or "Instagram Reel",
        "uploader":  post.owner_username,
        "duration":  int(post.video_duration) if post.is_video and post.video_duration else 0,
        "is_video":  post.is_video,
        "media_url": post.video_url if post.is_video else post.url,
    }


# ════════════════════════════════════════════════════════════
#  MESSAGE BUILDERS  (clean, professional)
# ════════════════════════════════════════════════════════════

def build_info_card(platform: str, title: str, uploader: str,
                    duration: int, views: int) -> str:
    icon = PLATFORM_ICON.get(platform, f"◈ {platform}")
    lines = [
        f"  {icon}",
        "  ─────────────────────────────",
        f"  {title}",
    ]
    if uploader:
        lines.append(f"  by  {uploader}")
    if duration:
        lines.append(f"  {fmt_duration(duration)}")
    if views:
        lines.append(f"  {fmt_views(views)} views")
    lines += [
        "  ─────────────────────────────",
        "  Choose format below",
    ]
    return "\n".join(lines)


def build_caption(platform: str, mode: str, size_mb: float) -> str:
    icon  = PLATFORM_ICON.get(platform, f"◈ {platform}")
    label = "Video" if mode == "video" else "Audio"
    return (
        f"  {icon}  ·  {label}\n"
        f"  {size_mb:.1f} MB\n\n"
        f"  {BOT_TAG}"
    )


# ════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register(update)
    name = update.effective_user.first_name or "there"
    if not await gate(update, context):
        return

    text = (
        f"  Welcome, {name}.\n\n"
        "  ─────────────────────────────────────\n"
        "  Send any video link and I will fetch\n"
        "  it as  Video  or  Audio  — your call.\n"
        "  ─────────────────────────────────────\n\n"
        "  Supported platforms\n\n"
        "  YouTube  ·  Instagram  ·  TikTok\n"
        "  Facebook  ·  Twitter/X  ·  Pinterest\n"
        "  Reddit  ·  Vimeo  ·  Dailymotion\n"
        "  SoundCloud\n\n"
        f"  {BOT_TAG}"
    )
    await update.message.reply_text(text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register(update)
    text = (
        "  How to use\n\n"
        "  1.  Open any supported app\n"
        "  2.  Find the video you want\n"
        "  3.  Share  →  Copy Link\n"
        "  4.  Paste the link here\n"
        "  5.  Tap  Video  or  Audio\n"
        "  6.  File arrives in this chat\n\n"
        "  ─────────────────────────────────────\n"
        "  Instagram links deliver a direct\n"
        "  save button instead of a file upload.\n"
        "  ─────────────────────────────────────\n\n"
        "  Content must be public to download."
    )
    await update.message.reply_text(text)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register(update)
    uid   = update.effective_user.id
    me    = user_db.get(uid, {})
    total = len(user_db)
    text = (
        "  Statistics\n\n"
        f"  Total users      {total}\n"
        f"  Your downloads   {me.get('downloads', 0)}\n"
        f"  Member since     {me.get('joined', '—')}\n\n"
        "  (Counters reset on bot restart)"
    )
    await update.message.reply_text(text)


# ════════════════════════════════════════════════════════════
#  CALLBACK:  join verification
# ════════════════════════════════════════════════════════════

async def cb_check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "there"

    if await is_member(uid, context):
        await query.message.edit_text(
            f"  Access granted, {name}.\n\n"
            "  Send me any video link to get started."
        )
    else:
        await query.message.edit_text(
            "  You have not joined yet.\n\n"
            "  Join the channel, then tap  ✓ I've Joined  again.",
            reply_markup=JOIN_KB,
        )


# ════════════════════════════════════════════════════════════
#  CALLBACK:  format selection  (Video / Audio)
# ════════════════════════════════════════════════════════════

async def cb_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Processing…")

    uid  = update.effective_user.id
    data = query.data   # "fmt_video_<uid>"  or  "fmt_audio_<uid>"

    try:
        _, mode, target = data.split("_", 2)
        if uid != int(target):
            await query.answer("This action belongs to another user.", show_alert=True)
            return
    except Exception:
        await query.message.edit_text("Invalid request — please send the link again.")
        return

    url = url_store.pop(uid, None)
    if not url:
        await query.message.edit_text(
            "  Session expired.\n\n  Please send your link again."
        )
        return

    platform = detect_platform(url)
    label    = "Video" if mode == "video" else "Audio"

    await query.message.edit_text(
        f"  Downloading  {label}  ·  {PLATFORM_ICON.get(platform, platform)}\n\n"
        "  Please wait…"
    )

    with tempfile.TemporaryDirectory() as tmp:
        try:
            fp      = await ydl_download(url, mode, tmp)
            size_mb = fp.stat().st_size / (1024 * 1024)

            if size_mb > 49:
                await query.message.edit_text(
                    f"  File too large  ({size_mb:.1f} MB)\n\n"
                    "  Telegram bots are limited to 49 MB.\n"
                    "  Try a shorter clip or switch to Audio."
                )
                return

            add_download(uid)
            caption = build_caption(platform, mode, size_mb)

            if mode == "audio":
                await context.bot.send_audio(
                    chat_id=query.message.chat_id,
                    audio=open(fp, "rb"),
                    caption=caption,
                )
            else:
                await context.bot.send_video(
                    chat_id=query.message.chat_id,
                    video=open(fp, "rb"),
                    caption=caption,
                    supports_streaming=True,
                )

            await query.message.delete()
            log.info("Delivered %s %s to uid=%s (%.1f MB)", platform, mode, uid, size_mb)

        except Exception as exc:
            log.error("Download error uid=%s: %s", uid, exc)
            await query.message.edit_text(
                "  Download failed.\n\n"
                f"  {str(exc)[:220]}\n\n"
                "  Ensure the content is public and the link is valid."
            )


# ════════════════════════════════════════════════════════════
#  MAIN MESSAGE HANDLER  —  receives URLs
# ════════════════════════════════════════════════════════════

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register(update)

    if not await gate(update, context):
        return

    url = update.message.text.strip()

    if not any(d in url.lower() for d in SUPPORTED_DOMAINS):
        await update.message.reply_text(
            "  Unsupported link.\n\n"
            "  Supported platforms:\n\n"
            "  YouTube  ·  Instagram  ·  TikTok\n"
            "  Facebook  ·  Twitter/X  ·  Pinterest\n"
            "  Reddit  ·  Vimeo  ·  Dailymotion\n"
            "  SoundCloud"
        )
        return

    uid      = update.effective_user.id
    platform = detect_platform(url)

    status = await update.message.reply_text(
        f"  Fetching  ·  {PLATFORM_ICON.get(platform, platform)}\n\n"
        "  One moment…"
    )

    # ── Instagram: instaloader direct-save button ──
    if "instagram.com" in url:
        try:
            meta = await ig_fetch(url)
            kb   = InlineKeyboardMarkup([[
                InlineKeyboardButton("Open & Save Video", url=meta["media_url"])
            ]])
            dur  = f"\n  Duration   {fmt_duration(meta['duration'])}" if meta["duration"] else ""
            await status.edit_text(
                f"  ◈ Instagram\n"
                f"  ─────────────────────────────\n"
                f"  {meta['title']}\n"
                f"  by  {meta['uploader']}"
                f"{dur}\n"
                f"  ─────────────────────────────\n"
                "  Tap below to open and save.",
                reply_markup=kb,
            )
        except Exception as exc:
            log.error("Instagram error: %s", exc)
            await status.edit_text(
                "  Instagram fetch failed.\n\n"
                f"  {str(exc)[:220]}\n\n"
                "  Make sure the post is public."
            )
        return

    # ── All other platforms: yt-dlp ──
    try:
        info     = await ydl_info(url)
        title    = (info.get("title") or "Untitled")[:72]
        uploader = info.get("uploader") or info.get("channel") or ""
        duration = int(info.get("duration") or 0)
        views    = int(info.get("view_count") or 0)

        url_store[uid] = url

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Video", callback_data=f"fmt_video_{uid}"),
            InlineKeyboardButton("Audio", callback_data=f"fmt_audio_{uid}"),
        ]])

        await status.edit_text(
            build_info_card(platform, title, uploader, duration, views),
            reply_markup=kb,
        )

    except Exception as exc:
        log.error("Info fetch error uid=%s: %s", uid, exc)
        await status.edit_text(
            "  Could not fetch media info.\n\n"
            f"  {str(exc)[:220]}\n\n"
            "  Make sure the link is public and correct."
        )


# ════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help",  cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))

    app.add_handler(CallbackQueryHandler(cb_check_join, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(cb_format,     pattern=r"^fmt_(video|audio)_\d+$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    log.info("Bot started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
