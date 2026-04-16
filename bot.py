import os
import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
BOT_TAG = "@your_bot_username"  # Change this to your bot username

# Storage
user_stats = {}
pending_urls = {}

# ═══════════════════════════════════════════════════════════════
# SUPPORTED PLATFORMS
# ═══════════════════════════════════════════════════════════════

SUPPORTED_DOMAINS = [
    "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
    "facebook.com", "fb.watch", "twitter.com", "x.com",
    "pinterest.com", "pin.it", "reddit.com", "redd.it",
    "vimeo.com", "dailymotion.com", "soundcloud.com"
]

PLATFORM_ICONS = {
    "youtube": "🎬 YouTube", "instagram": "📸 Instagram", "tiktok": "🎵 TikTok",
    "facebook": "📘 Facebook", "twitter": "🐦 Twitter", "pinterest": "📌 Pinterest",
    "reddit": "🤖 Reddit", "vimeo": "🎥 Vimeo", "dailymotion": "🎬 Dailymotion",
    "soundcloud": "🎧 SoundCloud"
}

def detect_platform(url):
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower: return "youtube"
    if "instagram.com" in url_lower: return "instagram"
    if "tiktok.com" in url_lower: return "tiktok"
    if "facebook.com" in url_lower or "fb.watch" in url_lower: return "facebook"
    if "twitter.com" in url_lower or "x.com" in url_lower: return "twitter"
    if "pinterest.com" in url_lower or "pin.it" in url_lower: return "pinterest"
    if "reddit.com" in url_lower or "redd.it" in url_lower: return "reddit"
    if "vimeo.com" in url_lower: return "vimeo"
    if "dailymotion.com" in url_lower: return "dailymotion"
    if "soundcloud.com" in url_lower: return "soundcloud"
    return "unknown"

def format_duration(seconds):
    if not seconds: return ""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"

def format_number(num):
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    if num >= 1000:
        return f"{num/1000:.1f}K"
    return str(num)

# ═══════════════════════════════════════════════════════════════
# YT-DLP FUNCTIONS
# ═══════════════════════════════════════════════════════════════

async def get_media_info(url):
    """Get media information without downloading"""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    
    loop = asyncio.get_event_loop()
    def extract():
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    
    return await loop.run_in_executor(None, extract)

async def get_download_url(info, media_type):
    """Extract direct download URL from media info"""
    
    if media_type == "audio":
        # Try to get best audio format
        formats = info.get("formats", [])
        audio_formats = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"]
        if audio_formats:
            best_audio = max(audio_formats, key=lambda x: x.get("abr", 0))
            return best_audio.get("url")
        return info.get("url")
    
    else:  # video
        # Try to get best video format (MP4 preferred)
        formats = info.get("formats", [])
        video_formats = [f for f in formats if f.get("ext") == "mp4" and f.get("vcodec") != "none"]
        if video_formats:
            best_video = max(video_formats, key=lambda x: x.get("height", 0))
            return best_video.get("url")
        return info.get("url")

# ═══════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name
    
    if user_id not in user_stats:
        user_stats[user_id] = {"name": user_name, "downloads": 0, "joined": datetime.now()}
    
    welcome_text = f"""
╔══════════════════════════════════╗
║     🎬 MEDIA DOWNLOADER BOT      ║
╚══════════════════════════════════╝

✨ **Welcome {user_name}!** ✨

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📥 **Send me any video link and I'll give you**
   **a DIRECT DOWNLOAD LINK!**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📱 **Supported Platforms:**

🎬 YouTube      📸 Instagram     🎵 TikTok
📘 Facebook     🐦 Twitter/X     📌 Pinterest
🤖 Reddit       🎥 Vimeo         🎬 Dailymotion
🎧 SoundCloud

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **How It Works:**

1️⃣ Copy link from any app
2️⃣ Paste link here
3️⃣ Choose Video or Audio
4️⃣ Click download button
5️⃣ Opens in browser → Auto-downloads! 🚀

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔰 **Commands:**

/start - Restart bot
/help  - Get help
/stats - Your statistics
/about - About this bot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{BOT_TAG}
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
╔══════════════════════════════════╗
║          📖 HELP GUIDE           ║
╚══════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**📥 HOW TO DOWNLOAD**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Open any supported app
2. Find the video you want
3. Tap **Share** → **Copy Link**
4. Paste the link in this chat
5. Select **Video** or **Audio**
6. Click the download button
7. **Download starts automatically!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**✅ FEATURES**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• 🎬 High quality video (MP4)
• 🎵 High quality audio (MP3)
• 🔗 Direct browser download
• 🚀 No login required
• 💯 Completely free
• 📊 Download statistics

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**⚠️ LIMITATIONS**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Max file size: 50MB (Telegram limit)
• Content must be public
• Some region-restricted videos may fail

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**🔰 COMMANDS**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/start - Restart bot
/help  - This help guide
/stats - View your statistics
/about - About this bot

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{BOT_TAG}
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = user_stats.get(user_id, {"downloads": 0, "joined": datetime.now()})
    
    stats_text = f"""
╔══════════════════════════════════╗
║         📊 YOUR STATS           ║
╚══════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 **User:** {user_stats.get(user_id, {}).get('name', 'User')}
📥 **Downloads:** {user_data.get('downloads', 0)}
📅 **Joined:** {user_data.get('joined', datetime.now()).strftime('%d %b %Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 **Total Users:** {len(user_stats)}

Keep downloading! 🚀
{BOT_TAG}
"""
    await update.message.reply_text(stats_text, parse_mode="Markdown")

async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    about_text = """
╔══════════════════════════════════╗
║          ℹ️ ABOUT BOT           ║
╚══════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Media Downloader Bot** v2.0

A powerful bot that downloads media from
multiple platforms and provides direct
download links.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**Supported Platforms:** 10+
**Downloads:** Unlimited
**Price:** FREE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**Developer:** @your_username
**Channel:** @your_channel

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{BOT_TAG}
"""
    await update.message.reply_text(about_text, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════════

async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data  # format: video_123456 or audio_123456
    
    try:
        media_type, original_user = data.split("_")
        if int(original_user) != user_id:
            await query.answer("This selection is not for you!", show_alert=True)
            return
    except:
        await query.edit_message_text("❌ Invalid selection. Please send the link again.")
        return
    
    url = pending_urls.get(user_id)
    if not url:
        await query.edit_message_text("⏰ Session expired. Please send your link again.")
        return
    
    # Show loading message
    await query.edit_message_text(
        f"🔄 **Processing {media_type.upper()} download...**\n\n"
        f"Getting direct link from server...\n"
        f"Please wait a moment ⏳",
        parse_mode="Markdown"
    )
    
    try:
        # Get media info
        info = await get_media_info(url)
        
        # Get direct download URL
        download_url = await get_download_url(info, media_type)
        
        if not download_url:
            raise Exception("Could not extract download URL")
        
        # Extract media details
        title = info.get("title", "Media")[:50]
        platform = detect_platform(url)
        platform_name = PLATFORM_ICONS.get(platform, "Media")
        duration = info.get("duration", 0)
        uploader = info.get("uploader", "")
        views = info.get("view_count", 0)
        
        # Update user stats
        if user_id in user_stats:
            user_stats[user_id]["downloads"] = user_stats[user_id].get("downloads", 0) + 1
        
        # Build info message
        info_message = f"""
✅ **DOWNLOAD READY!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 **Platform:** {platform_name}
📝 **Title:** {title}
{f'👤 **Uploader:** {uploader}' if uploader else ''}
{f'⏱️ **Duration:** {format_duration(duration)}' if duration else ''}
{f'👁️ **Views:** {format_number(views)}' if views else ''}
🎵 **Format:** {media_type.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**🔽 CLICK THE BUTTON BELOW 🔽**

➡️ It will open in your browser
➡️ Download starts **AUTOMATICALLY**
➡️ No login or registration needed!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{BOT_TAG}
"""
        
        # Create download button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 DOWNLOAD NOW", url=download_url)],
            [InlineKeyboardButton("🔄 Try Alternative", callback_data=f"alt_{media_type}_{user_id}")]
        ])
        
        await query.edit_message_text(info_message, reply_markup=keyboard, parse_mode="Markdown")
        
        # Clean up stored URL
        pending_urls.pop(user_id, None)
        
        log.info(f"✅ Download link generated for user {user_id} - {platform_name} - {media_type}")
        
    except Exception as e:
        log.error(f"Download error: {e}")
        await query.edit_message_text(
            f"❌ **DOWNLOAD FAILED**\n\n"
            f"**Error:** {str(e)[:150]}\n\n"
            f"**Possible solutions:**\n"
            f"• Make sure the video is public\n"
            f"• Try a different link\n"
            f"• Use the alternative format\n\n"
            f"Send /help for more assistance.",
            parse_mode="Markdown"
        )

async def handle_alternative(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Trying alternative method...")
    
    user_id = update.effective_user.id
    data = query.data  # format: alt_video_123456 or alt_audio_123456
    
    try:
        _, media_type, original_user = data.split("_")
        if int(original_user) != user_id:
            await query.answer("Not for you!", show_alert=True)
            return
    except:
        await query.edit_message_text("❌ Invalid request.")
        return
    
    url = pending_urls.get(user_id)
    if not url:
        await query.edit_message_text("⏰ Session expired. Send link again.")
        return
    
    await query.edit_message_text("🔄 **Trying alternative method...**\n\nPlease wait...", parse_mode="Markdown")
    
    try:
        # Try with different yt-dlp options
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "format": "best" if media_type == "video" else "bestaudio",
        }
        
        loop = asyncio.get_event_loop()
        def extract_alt():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get("url")
        
        download_url = await loop.run_in_executor(None, extract_alt)
        
        if download_url:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 DOWNLOAD NOW", url=download_url)]
            ])
            await query.edit_message_text(
                f"✅ **Alternative link generated!**\n\n"
                f"Click below to download:\n"
                f"➡️ Opens in browser\n"
                f"➡️ Auto-downloads!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            pending_urls.pop(user_id, None)
        else:
            raise Exception("No alternative URL found")
            
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Alternative method also failed**\n\n"
            f"Try these online downloaders:\n"
            f"• https://savefrom.net\n"
            f"• https://y2mate.com\n\n"
            f"Or try a different video link.",
            parse_mode="Markdown"
        )

# ═══════════════════════════════════════════════════════════════
# MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not update.message or not update.message.text:
        return
    
    url = update.message.text.strip()
    
    # Check if URL is supported
    if not any(domain in url.lower() for domain in SUPPORTED_DOMAINS):
        await update.message.reply_text(
            f"❌ **Unsupported Link**\n\n"
            f"Please send a link from:\n"
            f"🎬 YouTube • 📸 Instagram • 🎵 TikTok\n"
            f"📘 Facebook • 🐦 Twitter/X • 📌 Pinterest\n"
            f"🤖 Reddit • 🎥 Vimeo • 🎬 Dailymotion\n"
            f"🎧 SoundCloud\n\n"
            f"{BOT_TAG}",
            parse_mode="Markdown"
        )
        return
    
    # Show processing message
    processing_msg = await update.message.reply_text(
        f"🔍 **Fetching media information...**\n\n"
        f"⏳ Analyzing your link\n"
        f"Please wait...",
        parse_mode="Markdown"
    )
    
    try:
        # Get media info
        info = await get_media_info(url)
        
        # Store URL for later use
        pending_urls[user_id] = url
        
        # Extract media details
        title = info.get("title", "Untitled")[:60]
        platform = detect_platform(url)
        platform_name = PLATFORM_ICONS.get(platform, "Media")
        duration = info.get("duration", 0)
        uploader = info.get("uploader", "") or info.get("channel", "")
        views = info.get("view_count", 0)
        likes = info.get("like_count", 0)
        
        # Create format selection keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎬 VIDEO", callback_data=f"video_{user_id}"),
                InlineKeyboardButton("🎵 AUDIO", callback_data=f"audio_{user_id}")
            ]
        ])
        
        # Build info message
        info_message = f"""
╔══════════════════════════════════╗
║     📊 MEDIA INFORMATION        ║
╚══════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 **Platform:** {platform_name}
📝 **Title:** {title}
{f'👤 **Uploader:** {uploader}' if uploader else ''}
{f'⏱️ **Duration:** {format_duration(duration)}' if duration else ''}
{f'👁️ **Views:** {format_number(views)}' if views else ''}
{f'❤️ **Likes:** {format_number(likes)}' if likes else ''}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📥 SELECT YOUR FORMAT:**

🎬 **Video** - MP4 format (High quality)
🎵 **Audio** - MP3 format (192kbps)

Click a button below 👇
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{BOT_TAG}
"""
        
        await processing_msg.edit_text(info_message, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        log.error(f"Info fetch error: {e}")
        await processing_msg.edit_text(
            f"❌ **Failed to fetch media**\n\n"
            f"**Error:** {str(e)[:150]}\n\n"
            f"**Possible reasons:**\n"
            f"• Video is private or deleted\n"
            f"• Link is invalid\n"
            f"• Region restricted content\n\n"
            f"Try a different link!",
            parse_mode="Markdown"
        )

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN environment variable not set!")
        print("Please add BOT_TOKEN to your environment variables.")
        return
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("about", cmd_about))
    
    # Add callback handlers
    app.add_handler(CallbackQueryHandler(handle_format_selection, pattern=r"^(video|audio)_\d+$"))
    app.add_handler(CallbackQueryHandler(handle_alternative, pattern=r"^alt_(video|audio)_\d+$"))
    
    # Add message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start bot
    log.info("🚀 BOT STARTED SUCCESSFULLY!")
    log.info("✅ All features loaded")
    log.info("📱 Supported platforms: 10+")
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
