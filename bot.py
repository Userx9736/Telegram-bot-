import os
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL = "@joinpremiummodsx"

user_set = set()

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
        keyboard = [[InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/joinpremiummodsx")],
                    [InlineKeyboardButton("🔄 I Joined!", callback_data="check_join")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"👋 Hello {name}!\n\n"
            "⚠️ You must join our channel first to use this bot!\n\n"
            "👇 Click below to join:",
            reply_markup=reply_markup
        )
        return

    await update.message.reply_text(
        f"🤍 {name}, hi!\n\n"
        "🤖 This bot downloads videos, photos & audio from popular social networks!\n\n"
        "📖 How to use:\n"
        "1️⃣ Open any social network\n"
        "2️⃣ Choose the video you like\n"
        "3️⃣ Tap 'Copy link' button\n"
        "4️⃣ Send the link here & get your file!\n\n"
        "🔗 Supported platforms:\n"
        "▶️ YouTube • 🎵 TikTok\n"
        "📘 Facebook • 🐦 Twitter\n"
        "👽 Reddit • 📌 Pinterest\n\n"
        "💎 Join our channel for updates:\n"
        "👉 https://t.me/joinpremiummodsx\n\n"
        "✅ @reelsdownloadersbot"
    )

async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    name = update.effective_user.first_name

    if await is_member(update, context):
        await query.message.edit_text(
            f"🤍 {name}, hi!\n\n"
            "🤖 This bot downloads videos, photos & audio from popular social networks!\n\n"
            "📖 How to use:\n"
            "1️⃣ Open any social network\n"
            "2️⃣ Choose the video you like\n"
            "3️⃣ Tap 'Copy link' button\n"
            "4️⃣ Send the link here & get your file!\n\n"
            "🔗 Supported platforms:\n"
            "▶️ YouTube • 🎵 TikTok\n"
            "📘 Facebook • 🐦 Twitter\n"
            "👽 Reddit • 📌 Pinterest\n\n"
            "💎 Join our channel for updates:\n"
            "👉 https://t.me/joinpremiummodsx\n\n"
            "✅ @reelsdownloadersbot"
        )
    else:
        keyboard = [[InlineKeyboardButton("✅ Join Channel", url="https://t.me/joinpremiummodsx")],
                    [InlineKeyboardButton("🔄 I Joined!", callback_data="check_join")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text(
            "❌ You have not joined yet!\n\n"
            "Please join the channel first:",
            reply_markup=reply_markup
        )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_set.add(update.effective_user.id)

    if not await is_member(update, context):
        keyboard = [[InlineKeyboardButton("✅ Join Channel", url="https://t.me/joinpremiummodsx")],
                    [InlineKeyboardButton("🔄 I Joined!", callback_data="check_join")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ You must join our channel first!\n\n"
            "👇 Click below to join:",
            reply_markup=reply_markup
        )
        return

    url = update.message.text.strip()

    SUPPORTED = [
        "youtube.com", "youtu.be",
        "facebook.com", "fb.watch",
        "twitter.com", "x.com",
        "tiktok.com", "reddit.com",
        "pinterest.com"
    ]

    if not any(site in url for site in SUPPORTED):
        await update.message.reply_text(
            "⚠️ Please send a valid link!\n\n"
            "🔗 Supported platforms:\n"
            "▶️ YouTube • 🎵 TikTok\n"
            "📘 Facebook • 🐦 Twitter\n"
            "👽 Reddit • 📌 Pinterest"
        )
        return

    await update.message.reply_text("🔍 Processing your link... Please wait!")

    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if 'formats' in info:
                formats = [f for f in info['formats'] if f.get('url') and f.get('ext') == 'mp4']
                if formats:
                    video_url = formats[-1]['url']
                else:
                    video_url = info['formats'][-1]['url']
            else:
                video_url = info.get('url', '')

            title = info.get('title', 'Video')
            duration = info.get('duration', 0)

            if duration:
                minutes = duration // 60
                seconds = duration % 60
                duration_text = f"⏱ Duration: {minutes}m {seconds}s\n"
            else:
                duration_text = ""

        keyboard = [[InlineKeyboardButton("📥 Download Now", url=video_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ Found!\n\n"
            f"🎬 {title}\n"
            f"{duration_text}\n"
            f"👇 Click below to download!\n\n"
            f"💎 @reelsdownloadersbot",
            reply_markup=reply_markup
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Failed!\n\n"
            f"Reason: {str(e)[:200]}\n\n"
            "Please try:\n"
            "✅ Make sure video is public\n"
            "✅ Check the link is correct"
        )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 Bot Statistics\n\n"
        f"👥 Total Users: {len(user_set)}"
    )

app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CallbackQueryHandler(check_join, pattern="check_join"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()
