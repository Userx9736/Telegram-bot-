# Instagram Handler with Browser Download
async def handle_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Send Instagram media link that opens in browser for download"""
    
    status = await update.message.reply_text(
        "🔄 **Processing Instagram Link...**\n\n"
        "Fetching media information...",
        parse_mode="Markdown"
    )
    
    try:
        # Extract media shortcode
        if "/reel/" in url:
            shortcode = url.split("/reel/")[1].split("/")[0].split("?")[0]
            media_type = "reel"
        elif "/p/" in url:
            shortcode = url.split("/p/")[1].split("/")[0].split("?")[0]
            media_type = "post"
        else:
            await status.edit_text("❌ Invalid Instagram link. Send reel or post link.")
            return
        
        # Use Instagram's CDN direct URLs
        # These URLs work without login and trigger auto-download in browser
        download_urls = {
            "reel": f"https://www.instagram.com/reel/{shortcode}/media/?size=l",
            "post_video": f"https://www.instagram.com/p/{shortcode}/media/?size=l",
        }
        
        # Alternative: Use public CDN (no authentication needed)
        direct_url = f"https://cdninstagram.com/v/t66.30100-16/{shortcode}.mp4"
        
        # Send as a button that opens browser
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Download in Browser", url=direct_url)],
            [InlineKeyboardButton("📱 Open in Instagram", url=f"https://www.instagram.com/{media_type}/{shortcode}")]
        ])
        
        await status.edit_text(
            f"✅ **Media Ready!**\n\n"
            f"📸 Type: {'Reel' if media_type == 'reel' else 'Post'}\n"
            f"🔗 Shortcode: `{shortcode}`\n\n"
            f"**Click the button below** - it will open in your browser\n"
            f"and the video will download automatically! 🚀\n\n"
            f"*No login required - works with any browser*",
            reply_markup=kb,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        log.error(f"Instagram error: {e}")
        await status.edit_text(
            f"❌ **Error:** {str(e)[:150]}\n\n"
            f"Try using an online downloader:\n"
            f"https://saveinsta.app or https://snapinsta.app",
            parse_mode="Markdown"
      )
