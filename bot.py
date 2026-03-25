import os
import yt_dlp
import instaloader
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL = "@joinpremiummodsx"

user_set = set()
L = instaloader.Instaloader()

async def is_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        member = await context.bot.get_chat_member(CHANNEL, update.effective_user.id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_set.add(update.effective_user.id)
    name = update.effective_user.first_name

    if not await is_member(update, context):
        keyboard = [
            [InlineKeyboardButton("✅ Join Channel", url="https://t.me/joinpremiummodsx")],
            [InlineKeyboardButton("🔄 I Joined!", callback_data="check_join")]
        ]
        await update.message.reply_text(
            f"👋 Hello {name}!\n\n"
            "⚠️ Join our channel first to use this bot!\n\n"
            "👇 Click below to join:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await update.message.reply_text(
        f"🤍 {name}, hi!\n\n"
        "🤖 This bot downloads videos & photos from popular social networks!\n\n"
        "📖 How to use:\n"
        "1️⃣ Open any social network\n"
        "2️⃣ Choose the video you like\n"
        "3️⃣ Tap 'Copy link' button\n"
        "4️⃣ Send the link here!\n\n"
        "🔗 Supported platforms:\n"
        "▶️ YouTube • 📸 Instagram\n"
        "🎵 TikTok • 📘 Facebook\n"
        "🐦 Twitter • 📌 Pinterest\n\n"
        "💎 @reelsdownloadersbot"
    )

async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = update.effective_user.first_name

    if await is_member(update, context):
        await query.message.edit_text(
            f"✅ Welcome {name}!\n\n"
            "Now send me any video link to download! 🎬"
        )
    else:
        keyboard = [
            [InlineKeyboardButton("✅ Join Channel", url="https://t.me/joinpremiummodsx")],
            [InlineKeyboardButton("🔄 I Joined!", callback_data="check_join")]
        ]
        await query.message.edit_text(
            "❌ You have not joined yet!\n\n"
            "Please join the channel first:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def get_instagram_url(url):
    try:
        shortcode = url.split("/p/")[-1].split("/")[0] if "/p/" in url else url.split("/reel/")[-1].split("/")[0]
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        if post.is_video:
            return post.video_url, post.title or "Instagram Video"
        else:
            return post.url, "Instagram Photo"
    except Exception as e:
        raise Exception(f"Instagram error: {str(e)}")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_set.add(update.effective_user.id)

    if not await is_member(update, context):
        keyboard = [
            [InlineKeyboardButton("✅ Join Channel", url="https://t.me/joinpremiummodsx")],
            [InlineKeyboardButton("🔄 I Joined!", callback_data="check_join")]
        ]
        await update.message.reply_text(
            "⚠️ Join our channel first!\n\n"
            "👇♥️ Click below:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    url = update.message.text.strip()

    SUPPORTED = [
        "youtube.com", "youtu.be",
        "facebook.com", "fb.watch",
        "twitter.com", "x.com",
        "tiktok.com", "reddit.com",
        "pinterest.com", "instagram.com"
    ]

    if not any(site in url for site in SUPPORTED):
        await update.message.reply_text(
            "⚠️ Please send a valid link!\n\n"
            "🔗 Supported:\n"
            "▶️ YouTube • 📸 Instagram\n"
            "🎵 TikTok • 📘 Facebook\n"
            "🐦 Twitter • 📌 Pinterest"
        )
        return

    await update.message.reply_text("🔍 Processing... Please wait!")

    try:
        # Instagram
        if "instagram.com" in url:
            video_url, title = await get_instagram_url(url)
            keyboard = [[InlineKeyboardButton("📥 Download Now", url=video_url)]]
            await update.message.reply_text(
                f"✅ Found!\n\n"
                f"📸 {title}\n\n"
                f"👇 Click to download!\n\n"
                f"💥 @reelsdownloadersbot",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # All other platforms
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if 'formats' in info:
                formats = [f for f in info['formats'] if f.get('url') and f.get('ext') == 'mp4']
                video_url = formats[-1]['url'] if formats else info['formats'][-1]['url']
            else:
                video_url = info.get('url', '')

            title = info.get('title', 'Video')
            duration = info.get('duration', 0)
            duration_text = f"⏱ {duration//60}m {duration%60}s\n" if duration else ""

        keyboard = [[InlineKeyboardButton("📥 Download Now", url=video_url)]]
        await update.message.reply_text(
            f"✅ Found!\n\n"
            f"🎬 {title}\n"
            f"{duration_text}\n"
            f"👇 Click to download!\n\n"
            f"💥 @reelsdownloadersbot",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Failed!\n\n"
            f"Reason: {str(e)[:200]}\n\n"
            "✅ Make sure video is public\n"
            "✅ Check link is correct"
        )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 Bot Stats\n\n"
        f"👥 Total Users: {len(user_set)}"
    )

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CallbackQueryHandler(check_join, pattern="check_join"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()
