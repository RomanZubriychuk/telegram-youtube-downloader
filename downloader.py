import subprocess
import yt_dlp
from pathlib import Path
from typing import Callable, Optional
from config import DOWNLOAD_DIR


class DownloadProgress:
    def __init__(self, callback: Optional[Callable[[float, str], None]] = None):
        self.callback = callback
        self.last_percent = -1

    def hook(self, d: dict):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                percent = int(downloaded / total * 100)
                if percent != self.last_percent and self.callback:
                    self.last_percent = percent
                    self.callback(percent, "downloading")
        elif d["status"] == "finished":
            if self.callback:
                self.callback(100, "processing")


def get_video_info(url: str) -> dict:
    """Fetch video metadata without downloading."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "enable_remote_components": ["ejs:github"],
        "cookiesfrombrowser": ("chrome",),
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title") or "Unknown",
            "duration": info.get("duration") or 0,
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader") or "Unknown",
        }


def format_duration(seconds: int) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format."""
    if seconds < 3600:
        return f"{seconds // 60}:{seconds % 60:02d}"
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def download_video(
    url: str,
    quality: str = "best",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Path:
    """Download video with specified quality, ensuring iPhone compatibility (H.264 codec)."""
    progress = DownloadProgress(progress_callback)

    # Prefer H.264 codec for iPhone compatibility
    format_map = {
        "best": "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[vcodec^=avc1]+bestaudio/best[vcodec^=avc1]/best",
        "720p": "bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=720][vcodec^=avc1]+bestaudio/best[height<=720][vcodec^=avc1]/best[height<=720]",
        "480p": "bestvideo[height<=480][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=480][vcodec^=avc1]+bestaudio/best[height<=480][vcodec^=avc1]/best[height<=480]",
    }

    ydl_opts = {
        "format": format_map.get(quality, format_map["best"]),
        "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
        "progress_hooks": [progress.hook],
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "enable_remote_components": ["ejs:github"],
        "cookiesfrombrowser": ("chrome",),
        "postprocessor_args": {
            "Merger": ["-movflags", "+faststart"],
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        final_path = Path(filename)
        if not final_path.exists():
            final_path = final_path.with_suffix(".mp4")

        # Check if non-H.264 codec and need to re-encode
        vcodec = info.get("vcodec", "")
        if vcodec and not vcodec.startswith("avc"):
            # Re-encode to H.264 for iPhone
            h264_path = final_path.with_stem(final_path.stem + "_h264")
            subprocess.run([
                "ffmpeg", "-i", str(final_path),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                "-y", str(h264_path)
            ], check=True, capture_output=True)
            final_path.unlink()  # Remove original
            h264_path.rename(final_path)  # Rename to original name

        return final_path


def download_audio(
    url: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Path:
    """Extract audio (MP3)"""
    progress = DownloadProgress(progress_callback)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(DOWNLOAD_DIR / "%(title)s.%(ext)s"),
        "progress_hooks": [progress.hook],
        "quiet": True,
        "no_warnings": True,
        "enable_remote_components": ["ejs:github"],
        "cookiesfrombrowser": ("chrome",),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return Path(filename).with_suffix(".mp3")


def get_file_size_mb(path: Path) -> float:
    """Get file size in megabytes."""
    return path.stat().st_size / (1024 * 1024)
