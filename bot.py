import re
import asyncio
import hashlib
import logging
import threading
from html import escape
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from config import TELEGRAM_BOT_TOKEN
from downloader import (
    get_video_info,
    download_video,
    download_audio,
    format_duration,
    get_file_size_mb,
)
from fileserver import create_app, get_download_url, get_local_ip, SERVER_PORT

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

YOUTUBE_REGEX = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w-]+"
)

# Store URLs keyed by short hash to avoid Telegram's 64-byte callback_data limit
_url_store: dict[str, str] = {}
_URL_STORE_MAX = 100


def _store_url(url: str) -> str:
    """Store a URL and return a short key."""
    if len(_url_store) >= _URL_STORE_MAX:
        # Remove oldest half
        keys = list(_url_store.keys())
        for k in keys[:len(keys) // 2]:
            del _url_store[k]
    key = hashlib.md5(url.encode()).hexdigest()[:10]
    _url_store[key] = url
    return key


def _get_url(key: str) -> str | None:
    """Retrieve a URL by its short key."""
    return _url_store.get(key)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message."""
    ip = get_local_ip()
    await update.message.reply_text(
        "Welcome to YouTube Downloader Bot!\n\n"
        "Send me a YouTube link and I'll give you a download link.\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/help - Show help\n"
        f"/files - Browse all downloads\n\n"
        f"File server: http://{ip}:{SERVER_PORT}"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message."""
    await update.message.reply_text(
        "How to use:\n\n"
        "1. Send me a YouTube link\n"
        "2. I'll show you video info\n"
        "3. Choose download quality\n"
        "4. Click the download link I send you\n\n"
        "Supported links:\n"
        "- youtube.com/watch?v=...\n"
        "- youtu.be/...\n"
        "- youtube.com/shorts/...\n\n"
        "Note: Your device must be on the same network as this bot."
    )


async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send link to file browser."""
    ip = get_local_ip()
    await update.message.reply_text(
        f"Browse all downloads:\nhttp://{ip}:{SERVER_PORT}"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and detect YouTube URLs."""
    text = update.message.text
    match = YOUTUBE_REGEX.search(text)

    if not match:
        await update.message.reply_text(
            "Please send a valid YouTube link."
        )
        return

    url = match.group(0)
    if not url.startswith("http"):
        url = "https://" + url

    status_msg = await update.message.reply_text("Fetching video info...")

    try:
        info = await asyncio.get_running_loop().run_in_executor(
            None, get_video_info, url
        )

        duration = format_duration(info["duration"]) if info["duration"] else "Unknown"

        url_key = _store_url(url)
        keyboard = [
            [
                InlineKeyboardButton("Best Quality", callback_data=f"best|{url_key}"),
                InlineKeyboardButton("720p", callback_data=f"720p|{url_key}"),
            ],
            [
                InlineKeyboardButton("480p", callback_data=f"480p|{url_key}"),
                InlineKeyboardButton("Audio Only", callback_data=f"audio|{url_key}"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        title = escape(info["title"])
        uploader = escape(info["uploader"])

        await status_msg.edit_text(
            f"<b>{title}</b>\n\n"
            f"Duration: {duration}\n"
            f"Channel: {uploader}\n\n"
            "Select download quality:",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error fetching video info: {e}")
        await status_msg.edit_text(f"Error fetching video info: {str(e)}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quality selection callback."""
    query = update.callback_query
    await query.answer()

    data = query.data
    quality, url_key = data.split("|", 1)

    url = _get_url(url_key)
    if not url:
        await query.edit_message_text("Link expired. Please send the URL again.")
        return

    progress_msg = await query.edit_message_text("Starting download...")

    last_update = [0]
    lock = threading.Lock()

    def progress_callback(percent: float, status: str):
        with lock:
            last_update[0] = percent

    async def update_progress():
        last_shown = -1
        while True:
            await asyncio.sleep(2)
            with lock:
                percent = last_update[0]
            if percent != last_shown:
                last_shown = percent
                try:
                    if percent < 100:
                        await progress_msg.edit_text(
                            f"Downloading... {percent}%"
                        )
                    else:
                        await progress_msg.edit_text("Processing...")
                except Exception:
                    pass
            if percent >= 100:
                break

    progress_task = asyncio.create_task(update_progress())

    try:
        loop = asyncio.get_running_loop()

        if quality == "audio":
            filepath = await loop.run_in_executor(
                None, lambda: download_audio(url, progress_callback)
            )
        else:
            filepath = await loop.run_in_executor(
                None, lambda: download_video(url, quality, progress_callback)
            )

        progress_task.cancel()

        size_mb = get_file_size_mb(filepath)
        download_url = get_download_url(filepath.name)

        await progress_msg.edit_text(
            f"Ready to download!\n\n"
            f"File: {filepath.name}\n"
            f"Size: {size_mb:.1f} MB\n\n"
            f"Download: {download_url}"
        )

    except Exception as e:
        progress_task.cancel()
        logger.error(f"Download error: {e}")
        await progress_msg.edit_text(f"Download failed: {str(e)}")


async def run_bot():
    """Run the Telegram bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("files", files_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    return application


async def main():
    """Start both the file server and the bot."""
    ip = get_local_ip()
    logger.info(f"Starting file server at http://{ip}:{SERVER_PORT}")

    # Create and start file server
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", SERVER_PORT)
    await site.start()

    logger.info("Starting Telegram bot...")
    bot_app = await run_bot()

    logger.info("Bot is running! Press Ctrl+C to stop.")

    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
