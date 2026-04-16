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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL = "@joinpremiummodsx"  # Change to your channel
BOT_TAG = "@reelsdownloadersbot"  # Change to your bot username

# ── Instaloader instance ──────────────────────────────────────
_IL = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    save_metadata=False,
    quiet=True,
)

# ── Storage ──────────────────────────────────────────
user_db = {}
url_store = {}

# ════════════════════════════════════════════════════════════
#  SUPPORTED PLATFORMS
# ════════════════════════════════════════════════════════════

SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
    "facebook.com", "fb.watch", "twitter.com", "x.com",
    "pinterest.com", "pin.it", "reddit.com", "redd.it",
    "vimeo.com", "dailymotion.com", "soundcloud.com"
]

PLATFORM_ICON = {
    "YouTube": "🎬 YouTube", "Instagram": "📸 Instagram", "TikTok": "🎵 TikTok",
    "Twitter / X": "🐦 Twitter/X", "Facebook": "📘 Facebook", "Pinterest": "📌 Pinterest",
    "Reddit": "🤖 Reddit", "Vimeo": "🎥 Vimeo", "Dailymotion": "🎬 Dailymotion", "SoundCloud": "🎧 SoundCloud"
}

def detect_platform(url: str) -> str:
    u = url.lower()
    if any(d in u for d in ["youtube.com", "youtu.be"]): return "YouTube"
    if "instagram.com" in u: return "Instagram"
    if "tiktok.com" in u: return "TikTok"
    if any(d in u for d in ["facebook.com", "fb.watch"]): return "Facebook"
    if any(d in u for d in ["twitter.com", "x.com"]): return "Twitter / X"
    if any(d in u for d in ["pinterest.com", "pin.it"]): return "Pinterest"
    if any(d in u for d in ["reddit.com", "redd.it"]): return "Reddit"
    if "vimeo.com" in u: return "Vimeo"
    if "dailymotion.com" in u: return "Dailymotion"
    if "soundcloud.com" in u: return "SoundCloud"
    return "Unknown"

def fmt_duration(seconds: int) -> str:
    if not seconds: return ""
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"

# ════════════════════════════════════════════════════════════
#  CHANNEL VERIFICATION
# ════════════════════════════════════════════════════════════

JOIN_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{CHANNEL.lstrip('@')}")],
    [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")]
])

async def is_member(uid: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        m = await context.bot.get_chat_member(CHANNEL, uid)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

async def gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    uid = update.effective_user.id
    if await is_member(uid, context):
        return True
    
    text = "🔒 **Access Restricted**\n\nYou must join our channel to use this bot.\n\nClick below to join:"
    target = update.message or update.callback_query.message
    if target:
        if update.message:
            await target.reply_text(text, reply_markup=JOIN_KB, parse_mode="Markdown")
        else:
            await target.edit_text(text, reply_markup=JOIN_KB, parse_mode="Markdown")
    return False

# ════════════════════════════════════════════════════════════
#  YT-DLP FUNCTIONS
# ════════════════════════════════════════════════════════════

async def ydl_info(url: str) -> dict:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    loop = asyncio.get_event_loop()
    def _run():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    return await loop.run_in_executor(None, _run)

async def ydl_download(url: str, mode: str, outdir: str) -> Path:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(Path(outdir) / "%(title).60s.%(ext)s"),
    }
    
    if mode == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    else:
        opts["format"] = "best[ext=mp4][filesize<49M]/best"
        opts["merge_output_format"] = "mp4"
    
    loop = asyncio.get_event_loop()
    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    
    await loop.run_in_executor(None, _download)
    
    files = list(Path(outdir).iterdir())
    if files:
        return max(files, key=lambda f: f.stat().st_size)
    raise FileNotFoundError("No file downloaded")

# ════════════════════════════════════════════════════════════
#  INSTAGRAM FETCH
# ════════════════════════════════════════════════════════════

async def ig_fetch(url: str) -> dict:
    if "/reel/" in url:
        sc = url.split("/reel/")[1].split("/")[0].split("?")[0]
    elif "/p/" in url:
        sc = url.split("/p/")[1].split("/")[0].split("?")[0]
    else:
        raise ValueError("Send Instagram reel or post link")
    
    loop = asyncio.get_event_loop()
    post = await loop.run_in_executor(None, lambda: instaloader.Post.from_shortcode(_IL.context, sc))
    return {
        "title": (post.caption or "")[:72].strip() or "Instagram Post",
        "uploader": post.owner_username,
        "duration": int(post.video_duration) if post.is_video and post.video_duration else 0,
        "media_url": post.video_url if post.is_video else post.url,
    }

# ════════════════════════════════════════════════════════════
#  COMMANDS
# ════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_db:
        user_db[uid] = {"name": update.effective_user.first_name, "downloads": 0, "joined": datetime.now().strftime("%d %b %Y")}
    
    if not await gate(update, context):
        return
    
    text = f"""
✨ **Welcome {update.effective_user.first_name}!** ✨

━━━━━━━━━━━━━━━━━━━━━━━━
📥 **Media Downloader Bot**
━━━━━━━━━━━━━━━━━━━━━━━━

🎬 Send me any video link and I'll fetch it as:
• **Video** (MP4 format)
• **Audio** (MP3 format)

━━━━━━━━━━━━━━━━━━━━━━━━
📱 **Supported Platforms**
━━━━━━━━━━━━━━━━━━━━━━━━

🎯 YouTube • 📸 Instagram • 🎵 TikTok
📘 Facebook • 🐦 Twitter/X • 📌 Pinterest
🤖 Reddit • 🎥 Vimeo • 🎬 Dailymotion
🎧 SoundCloud

━━━━━━━━━━━━━━━━━━━━━━━━
💡 **How to use:**
1. Copy link from any app
2. Paste here
3. Choose Video or Audio
4. Download instantly!

━━━━━━━━━━━━━━━━━━━━━━━━
🔰 **Commands:**
/start - Restart bot
/help - Get help
/stats - Your statistics

━━━━━━━━━━━━━━━━━━━━━━━━
{ BOT_TAG }
"""
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📖 **Help Guide**

━━━━━━━━━━━━━━━━━━━━━━━━
**How to Download:**
━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ Open any supported app
2️⃣ Find the video you want
3️⃣ Tap Share → Copy Link
4️⃣ Paste the link here
5️⃣ Select **Video** or **Audio**
6️⃣ File will be sent instantly!

━━━━━━━━━━━━━━━━━━━━━━━━
**Instagram Notes:**
━━━━━━━━━━━━━━━━━━━━━━━━
• Instagram gives a direct save button
• Tap to open video, then save to device

━━━━━━━━━━━━━━━━━━━━━━━━
**Limitations:**
━━━━━━━━━━━━━━━━━━━━━━━━
• Max file size: 49MB (Telegram limit)
• Content must be public
• Private videos cannot be downloaded

━━━━━━━━━━━━━━━━━━━━━━━━
**Commands:**
/start - Restart bot
/help - Show this help
/stats - View your stats

━━━━━━━━━━━━━━━━━━━━━━━━
{ BOT_TAG }
"""
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    me = user_db.get(uid, {})
    total = len(user_db)
    text = f"""
📊 **Your Statistics**

━━━━━━━━━━━━━━━━━━━━━━━━
👥 Total Users: **{total}**
📥 Your Downloads: **{me.get('downloads', 0)}**
📅 Member Since: **{me.get('joined', 'Today')}**
━━━━━━━━━━━━━━━━━━━━━━━━

Keep downloading! 🚀
"""
    await update.message.reply_text(text, parse_mode="Markdown")

# ════════════════════════════════════════════════════════════
#  CALLBACKS
# ════════════════════════════════════════════════════════════

async def cb_check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    
    if await is_member(uid, context):
        await query.edit_message_text(
            "✅ **Access Granted!**\n\nSend me any video link to get started.",
            parse_mode="Markdown"
        )
    else:
        await query.edit_message_text(
            "❌ **Not Joined Yet**\n\nPlease join our channel first, then click 'I've Joined' again.",
            reply_markup=JOIN_KB,
            parse_mode="Markdown"
        )

async def cb_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Processing...")
    
    uid = update.effective_user.id
    data = query.data
    
    try:
        _, mode, target = data.split("_", 2)
        if uid != int(target):
            await query.answer("This action belongs to another user!", show_alert=True)
            return
    except:
        await query.edit_message_text("❌ Invalid request. Please send the link again.")
        return
    
    url = url_store.pop(uid, None)
    if not url:
        await query.edit_message_text("⏰ Session expired. Please send your link again.")
        return
    
    platform = detect_platform(url)
    await query.edit_message_text(
        f"📥 **Downloading {mode.upper()}**\n\n"
        f"🎬 Platform: {PLATFORM_ICON.get(platform, platform)}\n"
        f"⏳ Status: Processing...\n\n"
        f"Please wait, this may take a few seconds.",
        parse_mode="Markdown"
    )
    
    with tempfile.TemporaryDirectory() as tmp:
        try:
            fp = await ydl_download(url, mode, tmp)
            size_mb = fp.stat().st_size / (1024 * 1024)
            
            if size_mb > 49:
                await query.edit_message_text(
                    f"⚠️ **File Too Large**\n\n"
                    f"Size: {size_mb:.1f} MB\n"
                    f"Limit: 49 MB\n\n"
                    f"Try a shorter video or use Audio format.",
                    parse_mode="Markdown"
                )
                return
            
            if uid in user_db:
                user_db[uid]["downloads"] = user_db[uid].get("downloads", 0) + 1
            
            caption = f"✅ **Download Complete!**\n\n🎬 {PLATFORM_ICON.get(platform, platform)}\n📦 Size: {size_mb:.1f} MB\n\n{BOT_TAG}"
            
            with open(fp, "rb") as f:
                if mode == "audio":
                    await context.bot.send_audio(
                        chat_id=query.message.chat_id,
                        audio=f,
                        caption=caption,
                        parse_mode="Markdown"
                    )
                else:
                    await context.bot.send_video(
                        chat_id=query.message.chat_id,
                        video=f,
                        caption=caption,
                        supports_streaming=True,
                        parse_mode="Markdown"
                    )
            
            await query.message.delete()
            log.info(f"✅ Delivered {platform} {mode} to {uid} ({size_mb:.1f} MB)")
            
        except Exception as e:
            log.error(f"❌ Download error: {e}")
            await query.edit_message_text(
                f"❌ **Download Failed**\n\n"
                f"Error: {str(e)[:200]}\n\n"
                f"Possible reasons:\n"
                f"• Video is private\n"
                f"• Link is invalid\n"
                f"• Content not available\n\n"
                f"Try another link!",
                parse_mode="Markdown"
            )

# ════════════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ════════════════════════════════════════════════════════════

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in user_db:
        user_db[uid] = {"name": update.effective_user.first_name, "downloads": 0, "joined": datetime.now().strftime("%d %b %Y")}
    
    if not await gate(update, context):
        return
    
    if not update.message or not update.message.text:
        return
    
    url = update.message.text.strip()
    
    if not any(d in url.lower() for d in SUPPORTED_DOMAINS):
        await update.message.reply_text(
            "❌ **Unsupported Link**\n\n"
            "Supported platforms:\n"
            "🎬 YouTube • 📸 Instagram • 🎵 TikTok\n"
            "📘 Facebook • 🐦 Twitter/X • 📌 Pinterest\n"
            "🤖 Reddit • 🎥 Vimeo • 🎬 Dailymotion\n"
            "🎧 SoundCloud\n\n"
            f"Send a valid link from these platforms! {BOT_TAG}",
            parse_mode="Markdown"
        )
        return
    
    platform = detect_platform(url)
    status = await update.message.reply_text(
        f"🔍 **Fetching Media...**\n\n"
        f"🎬 Platform: {PLATFORM_ICON.get(platform, platform)}\n"
        f"⏳ Status: Analyzing link...\n\n"
        f"Please wait!",
        parse_mode="Markdown"
    )
    
    # Instagram special handling
    if "instagram.com" in url:
        try:
            meta = await ig_fetch(url)
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎬 Open & Save Video", url=meta["media_url"])
            ]])
            dur = f"\n⏱️ Duration: {fmt_duration(meta['duration'])}" if meta["duration"] else ""
            await status.edit_text(
                f"📸 **Instagram Media Found**\n\n"
                f"📝 {meta['title']}\n"
                f"👤 by {meta['uploader']}{dur}\n\n"
                f"Tap below to open and save to your device!",
                reply_markup=kb,
                parse_mode="Markdown"
            )
        except Exception as e:
            log.error(f"Instagram error: {e}")
            await status.edit_text(
                f"❌ **Instagram Error**\n\n"
                f"{str(e)[:200]}\n\n"
                f"Make sure the post is public!",
                parse_mode="Markdown"
            )
        return
    
    # Other platforms
    try:
        info = await ydl_info(url)
        title = info.get("title", "Untitled")[:72]
        uploader = info.get("uploader", "")
        duration = info.get("duration", 0)
        views = info.get("view_count", 0)
        
        url_store[uid] = url
        
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎬 Video", callback_data=f"fmt_video_{uid}"),
                InlineKeyboardButton("🎵 Audio", callback_data=f"fmt_audio_{uid}")
            ]
        ])
        
        text = f"""
🎬 **{PLATFORM_ICON.get(platform, platform)}**

━━━━━━━━━━━━━━━━━━━━━━━━
📝 **{title}**
{f'👤 **by** {uploader}' if uploader else ''}
{f'⏱️ **Duration:** {fmt_duration(duration)}' if duration else ''}
{f'👁️ **Views:** {views:,}' if views else ''}
━━━━━━━━━━━━━━━━━━━━━━━━

**Choose your format:**
"""
        await status.edit_text(text, reply_markup=kb, parse_mode="Markdown")
        
    except Exception as e:
        log.error(f"Info fetch error: {e}")
        await status.edit_text(
            f"❌ **Error Fetching Media**\n\n"
            f"{str(e)[:200]}\n\n"
            f"Possible reasons:\n"
            f"• Video is private\n"
            f"• Link is invalid\n"
            f"• Region restricted\n\n"
            f"Try another link!",
            parse_mode="Markdown"
        )

# ════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN not set! Add it in environment variables.")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CallbackQueryHandler(cb_check_join, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(cb_format, pattern=r"^fmt_(video|audio)_\d+$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    
    log.info("🚀 Bot started successfully!")
    app.run_polling()

if __name__ == "__main__":
    main()
