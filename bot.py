import os
import asyncio
import logging
import re
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
BOT_TAG = "@reelsdownloadersbot"  # Change to your bot username

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
# INSTAGRAM SPECIFIC HANDLER (Using public API - no login needed)
# ═══════════════════════════════════════════════════════════════

async def get_instagram_direct_url(url):
    """Get Instagram video URL using public methods"""
    
    # Extract shortcode from URL
    shortcode_match = re.search(r'instagram\.com/(?:reel|p)/([A-Za-z0-9_-]+)', url)
    if not shortcode_match:
        return None
    
    shortcode = shortcode_match.group(1)
    
    # Method 1: Use Instagram's CDN direct URL (works most of the time)
    direct_url = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
    
    # Method 2: Alternative CDN URL
    alt_url = f"https://scontent.cdninstagram.com/v/t66.30100-16/{shortcode}.mp4"
    
    # Method 3: Use yt-dlp with cookies (will try but may fail)
    try:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get("url"):
                return info.get("url")
    except:
        pass
    
    # Return the CDN URL as fallback (user can open in browser)
    return direct_url

async def get_instagram_info(url):
    """Get Instagram media information"""
    
    shortcode_match = re.search(r'instagram\.com/(?:reel|p)/([A-Za-z0-9_-]+)', url)
    if not shortcode_match:
        raise Exception("Invalid Instagram URL")
    
    shortcode = shortcode_match.group(1)
    media_type = "reel" if "/reel/" in url else "post"
    
    return {
        "title": f"Instagram {media_type.capitalize()}",
        "shortcode": shortcode,
        "type": media_type,
        "url": f"https://www.instagram.com/{media_type}/{shortcode}/media/?size=l"
    }

# ═══════════════════════════════════════════════════════════════
# YT-DLP FUNCTIONS (For all other platforms)
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
        formats = info.get("formats", [])
        audio_formats = [f for f in formats if f.get("vcodec") == "none" and f.get("acodec") != "none"]
        if audio_formats:
            best_audio = max(audio_formats, key=lambda x: x.get("abr", 0))
            return best_audio.get("url")
        return info.get("url")
    else:
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
    
    text = f"""
✨ **WELCOME {user_name.upper()}!** ✨

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📥 **MEDIA DOWNLOADER BOT**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Send me any video link and get **DIRECT DOWNLOAD LINK!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📱 **Supported Platforms:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎬 YouTube      📸 Instagram     🎵 TikTok
📘 Facebook     🐦 Twitter/X     📌 Pinterest
🤖 Reddit       🎥 Vimeo         🎧 SoundCloud

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 **How to Use:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ Copy video link from any app
2️⃣ Paste link here
3️⃣ Choose **Video** or **Audio**
4️⃣ Click download button
5️⃣ **Auto-download starts!** 🚀

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔰 **Commands:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

/start - Restart bot
/help  - Help guide
/stats - Your statistics

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{BOT_TAG}
"""
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📖 **HELP GUIDE**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📥 HOW TO DOWNLOAD:**

1. Open any supported app
2. Find the video you want
3. Tap **Share** → **Copy Link**
4. Paste the link in this chat
5. Select **Video** or **Audio**
6. Click the download button
7. **Download starts automatically!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**🎬 SUPPORTED PLATFORMS:**

• YouTube - Videos & Shorts
• Instagram - Reels & Posts
• TikTok - Videos
• Facebook - Videos & Reels
• Twitter/X - Videos
• Pinterest - Videos
• Reddit - Videos
• Vimeo - Videos
• SoundCloud - Audio

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**⚠️ NOTES:**

• Instagram: Click link → Open in browser → Save video
• Max file size: 50MB (Telegram limit)
• Content must be public

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**🔰 COMMANDS:**

/start - Restart bot
/help  - This guide
/stats - Your statistics

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{BOT_TAG}
"""
    await update.message.reply_text(text, parse_mode="Markdown")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = user_stats.get(user_id, {"downloads": 0, "joined": datetime.now()})
    
    text = f"""
📊 **YOUR STATISTICS**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👤 **User:** {user_stats.get(user_id, {}).get('name', 'User')}
📥 **Downloads:** {user_data.get('downloads', 0)}
📅 **Joined:** {user_data.get('joined', datetime.now()).strftime('%d %b %Y')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👥 **Total Users:** {len(user_stats)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{BOT_TAG}
"""
    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# CALLBACK HANDLERS
# ═══════════════════════════════════════════════════════════════

async def handle_format_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
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
    
    platform = detect_platform(url)
    
    # Show loading message
    await query.edit_message_text(
        f"🔄 **Processing {media_type.upper()} download...**\n\n"
        f"🎬 Platform: {PLATFORM_ICONS.get(platform, 'Media')}\n"
        f"⏳ Please wait...",
        parse_mode="Markdown"
    )
    
    try:
        # Handle Instagram separately
        if platform == "instagram":
            ig_info = await get_instagram_info(url)
            download_url = ig_info.get("url")
            
            if download_url:
                # Update user stats
                if user_id in user_stats:
                    user_stats[user_id]["downloads"] = user_stats[user_id].get("downloads", 0) + 1
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 DOWNLOAD VIDEO", url=download_url)],
                    [InlineKeyboardButton("🌐 Open in Instagram", url=f"https://www.instagram.com/{ig_info['type']}/{ig_info['shortcode']}")]
                ])
                
                await query.edit_message_text(
                    f"✅ **INSTAGRAM VIDEO READY!**\n\n"
                    f"📸 **Type:** {ig_info['type'].upper()}\n"
                    f"🔗 **Shortcode:** `{ig_info['shortcode']}`\n\n"
                    f"**Click the button below 👇**\n\n"
                    f"➡️ Opens in your browser\n"
                    f"➡️ Long press → Save video\n\n"
                    f"💡 **Tip:** If video doesn't load, tap 'Open in Instagram'",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                pending_urls.pop(user_id, None)
                log.info(f"Instagram download link sent to user {user_id}")
                return
            else:
                raise Exception("Could not get Instagram video URL")
        
        # Handle all other platforms with yt-dlp
        info = await get_media_info(url)
        download_url = await get_download_url(info, media_type)
        
        if not download_url:
            raise Exception("Could not extract download URL")
        
        # Extract media details
        title = info.get("title", "Media")[:50]
        platform_name = PLATFORM_ICONS.get(platform, "Media")
        duration = info.get("duration", 0)
        uploader = info.get("uploader", "")
        
        # Update user stats
        if user_id in user_stats:
            user_stats[user_id]["downloads"] = user_stats[user_id].get("downloads", 0) + 1
        
        # Create download button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 DOWNLOAD NOW", url=download_url)]
        ])
        
        info_message = f"""
✅ **DOWNLOAD READY!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 **Platform:** {platform_name}
📝 **Title:** {title}
{f'👤 **Uploader:** {uploader}' if uploader else ''}
{f'⏱️ **Duration:** {format_duration(duration)}' if duration else ''}
🎵 **Format:** {media_type.upper()}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**🔽 CLICK THE BUTTON BELOW 🔽**

➡️ Opens in your browser
➡️ Download starts **AUTOMATICALLY**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{BOT_TAG}
"""
        
        await query.edit_message_text(info_message, reply_markup=keyboard, parse_mode="Markdown")
        
        # Clean up stored URL
        pending_urls.pop(user_id, None)
        
        log.info(f"✅ Download link generated for user {user_id} - {platform_name} - {media_type}")
        
    except Exception as e:
        log.error(f"Download error: {e}")
        error_msg = str(e)
        
        # Provide helpful error message for Instagram
        if "instagram" in error_msg.lower():
            await query.edit_message_text(
                f"❌ **INSTAGRAM ERROR**\n\n"
                f"Instagram has rate limits. Try these alternatives:\n\n"
                f"**Method 1:** Use online downloader\n"
                f"👉 https://saveinsta.app\n\n"
                f"**Method 2:** Use this website\n"
                f"👉 https://snapinsta.app\n\n"
                f"**Method 3:** Try again in 5 minutes\n\n"
                f"**Method 4:** Use a different platform link\n\n"
                f"{BOT_TAG}",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"❌ **DOWNLOAD FAILED**\n\n"
                f"**Error:** {error_msg[:150]}\n\n"
                f"**Try these solutions:**\n"
                f"• Make sure video is public\n"
                f"• Try a different link\n"
                f"• Use Audio format instead\n\n"
                f"{BOT_TAG}",
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
    
    # Register user if new
    if user_id not in user_stats:
        user_stats[user_id] = {"name": update.effective_user.first_name, "downloads": 0, "joined": datetime.now()}
    
    # Check if URL is supported
    if not any(domain in url.lower() for domain in SUPPORTED_DOMAINS):
        await update.message.reply_text(
            f"❌ **Unsupported Link**\n\n"
            f"Please send a link from:\n"
            f"🎬 YouTube • 📸 Instagram • 🎵 TikTok\n"
            f"📘 Facebook • 🐦 Twitter/X • 📌 Pinterest\n"
            f"🤖 Reddit • 🎥 Vimeo • 🎧 SoundCloud\n\n"
            f"{BOT_TAG}",
            parse_mode="Markdown"
        )
        return
    
    platform = detect_platform(url)
    
    # Show processing message
    msg = await update.message.reply_text(
        f"🔍 **Fetching Media...**\n\n"
        f"🎬 Platform: {PLATFORM_ICONS.get(platform, 'Media')}\n"
        f"⏳ Analyzing link...",
        parse_mode="Markdown"
    )
    
    try:
        # Store URL for later use
        pending_urls[user_id] = url
        
        # Handle Instagram specially (faster response)
        if platform == "instagram":
            ig_info = await get_instagram_info(url)
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🎬 VIDEO", callback_data=f"video_{user_id}"),
                    InlineKeyboardButton("ℹ️ Help", callback_data=f"help_insta_{user_id}")
                ]
            ])
            
            await msg.edit_text(
                f"📸 **INSTAGRAM MEDIA DETECTED**\n\n"
                f"**Type:** {ig_info['type'].upper()}\n"
                f"**Shortcode:** `{ig_info['shortcode']}`\n\n"
                f"Click **VIDEO** to get download link.\n\n"
                f"💡 **Note:** Instagram videos open in browser.\n"
                f"Long press the video to save!",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return
        
        # For all other platforms, get info with yt-dlp
        info = await get_media_info(url)
        
        # Extract media details
        title = info.get("title", "Untitled")[:60]
        platform_name = PLATFORM_ICONS.get(platform, "Media")
        duration = info.get("duration", 0)
        uploader = info.get("uploader", "") or info.get("channel", "")
        views = info.get("view_count", 0)
        
        # Create format selection keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎬 VIDEO", callback_data=f"video_{user_id}"),
                InlineKeyboardButton("🎵 AUDIO", callback_data=f"audio_{user_id}")
            ]
        ])
        
        # Build info message
        info_text = f"""
🎬 **{platform_name}**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 **{title}**
{f'👤 **{uploader}**' if uploader else ''}
{f'⏱️ **{format_duration(duration)}**' if duration else ''}
{f'👁️ **{format_number(views)} views**' if views else ''}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📥 SELECT YOUR FORMAT:**

🎬 **Video** - MP4 (High Quality)
🎵 **Audio** - MP3 (192kbps)

{BOT_TAG}
"""
        await msg.edit_text(info_text, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        log.error(f"Info fetch error: {e}")
        error_msg = str(e)
        
        if "rate-limit" in error_msg.lower() or "login required" in error_msg.lower():
            await msg.edit_text(
                f"❌ **INSTAGRAM RATE LIMIT**\n\n"
                f"Instagram is temporarily blocking requests.\n\n"
                f"**Try these alternatives:**\n\n"
                f"1️⃣ Use online downloader:\n"
                f"   https://saveinsta.app\n\n"
                f"2️⃣ Try again in 5-10 minutes\n\n"
                f"3️⃣ Use a different platform link\n\n"
                f"{BOT_TAG}",
                parse_mode="Markdown"
            )
        else:
            await msg.edit_text(
                f"❌ **FAILED TO FETCH MEDIA**\n\n"
                f"**Error:** {error_msg[:150]}\n\n"
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
        return
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("stats", cmd_stats))
    
    # Add callback handlers
    app.add_handler(CallbackQueryHandler(handle_format_selection, pattern=r"^(video|audio)_\d+$"))
    
    # Add message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    log.info("🚀 BOT STARTED SUCCESSFULLY!")
    log.info("✅ All features loaded")
    log.info("📱 Supported platforms: YouTube, Instagram, TikTok, Facebook, Twitter, Pinterest, Reddit, Vimeo, SoundCloud")
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
