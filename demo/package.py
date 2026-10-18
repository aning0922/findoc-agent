"""Identity and response policy for the bundled, reviewed static demo."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREFIX = "projects/findoc/"
READING = PREFIX + "reading-v2/"
HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'self'; img-src 'self'; script-src 'none'; connect-src 'none'; form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cache-Control": "no-store",
}

def require(condition, message):
    if not condition:
        raise ValueError(message)

def spec(raw):
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
