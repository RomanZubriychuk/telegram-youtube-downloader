# Telegram YouTube Downloader

A Telegram bot that downloads YouTube videos/audio to your machine and serves download links over your local network.

## Setup

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram and copy the token

2. Create `.env` file:
   ```
   TELEGRAM_BOT_TOKEN=your_token_here
   ```

3. Install dependencies:
   ```bash
   brew install deno ffmpeg
   pip install -r requirements.txt
   ```

4. Run:
   ```bash
   python bot.py
   ```

## Usage

Send a YouTube link to your bot in Telegram, select quality, and get a download link.

Your device must be on the same network as the machine running the bot.

## Bot Commands

- `/start` - Welcome message
- `/help` - Usage instructions
- `/files` - Browse all downloaded files

## Download Options

- **Best Quality** - Highest available resolution (H.264)
- **720p** / **480p** - Lower resolution
- **Audio Only** - MP3 extraction

## Files

Downloads are saved to `~/Downloads/telegram-youtube/`.

A local file server runs on port 8080 for direct downloads.
