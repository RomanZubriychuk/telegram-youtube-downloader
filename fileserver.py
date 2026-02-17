import socket
import urllib.parse
from pathlib import Path
from xml.sax.saxutils import escape

from aiohttp import web
from config import DOWNLOAD_DIR

SERVER_PORT = 8080


def get_local_ip() -> str:
    """Get the local IP address for LAN access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


async def handle_download(request: web.Request) -> web.Response:
    """Handle file download requests."""
    filename = request.match_info.get("filename", "")
    filename = urllib.parse.unquote(filename)
    filepath = DOWNLOAD_DIR / filename

    # Ensure file is within download directory (check BEFORE existence)
    try:
        filepath.resolve().relative_to(DOWNLOAD_DIR.resolve())
    except ValueError:
        return web.Response(status=403, text="Access denied")

    if not filepath.exists() or not filepath.is_file():
        return web.Response(status=404, text="File not found")

    # Sanitize filename
    safe_name = filename.replace('"', "'").replace("\n", " ").replace("\r", " ")
    encoded_name = urllib.parse.quote(filename)

    return web.FileResponse(
        filepath,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_name}"; '
                f"filename*=UTF-8''{encoded_name}"
            )
        }
    )


async def handle_index(request: web.Request) -> web.Response:
    """List available files."""
    files = sorted(DOWNLOAD_DIR.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)

    html = "<html><head><title>Downloads</title></head><body>"
    html += "<h1>Downloaded Files</h1><ul>"

    for f in files[:20]:
        if f.is_file():
            encoded_name = urllib.parse.quote(f.name)
            size_mb = f.stat().st_size / (1024 * 1024)
            html += f'<li><a href="/download/{encoded_name}">{escape(f.name)}</a> ({size_mb:.1f} MB)</li>'

    html += "</ul></body></html>"
    return web.Response(text=html, content_type="text/html")


def create_app() -> web.Application:
    """Create the web application."""
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/download/{filename:.+}", handle_download)
    return app


def get_download_url(filename: str) -> str:
    """Generate download URL for a file."""
    ip = get_local_ip()
    encoded_name = urllib.parse.quote(filename)
    return f"http://{ip}:{SERVER_PORT}/download/{encoded_name}"
