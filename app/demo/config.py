"""Server-only demo configuration and versioned, slow password hashes."""
from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import secrets


def password_hash(password: str, *, iterations: int = 600_000) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def validate_hash(encoded: str) -> None:
    try:
        scheme, rounds, salt, digest = encoded.split("$")
        assert scheme == "pbkdf2_sha256" and 100_000 <= int(rounds) <= 2_000_000
        assert len(bytes.fromhex(salt)) >= 16 and len(bytes.fromhex(digest)) == 32
    except (ValueError, AssertionError) as exc:
        raise ValueError("Expected pbkdf2_sha256 hash with 100000..2000000 rounds") from exc


def verify_password(password: str, encoded: str) -> bool:
    scheme, rounds, salt, expected = encoded.split("$")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(actual.hex(), expected)


@dataclass(frozen=True)
class DemoConfig:
    control_root: Path
    seed_root: Path
    username: str
    password_hash: str
    origins: tuple[str, ...]
    owner_password_hash: str | None = None
    ttl_minutes: int = 20
    conflict_policy: str = "wait_only"
    secure_cookie: bool = True
    pending_seconds: int = 300

    def __post_init__(self) -> None:
        validate_hash(self.password_hash)
        if self.owner_password_hash:
            validate_hash(self.owner_password_hash)
        if self.ttl_minutes not in (20, 30):
            raise ValueError("DEMO_TTL_MINUTES must be 20 or 30")
        if self.conflict_policy not in ("wait_only", "takeover_enabled"):
            raise ValueError("Invalid DEMO_CONFLICT_POLICY")
        if self.conflict_policy == "takeover_enabled" and not self.owner_password_hash:
            raise ValueError("Takeover requires DEMO_OWNER_PASSWORD_HASH")
        if not self.username or not self.origins or any(o.endswith("/") for o in self.origins):
            raise ValueError("Explicit username and exact origins (without trailing slash) required")
        if not self.control_root.is_absolute() or not self.seed_root.is_absolute():
            raise ValueError("Absolute isolated control/seed paths required")
        control, seed = self.control_root.resolve(), self.seed_root.resolve()
        if control == seed or control in seed.parents or seed in control.parents:
            raise ValueError("Seed and control roots must be separate")

    @classmethod
    def from_env(cls) -> "DemoConfig":
        return cls(
            control_root=Path(os.environ["DEMO_CONTROL_ROOT"]),
            seed_root=Path(os.environ["DEMO_SEED_ROOT"]),
            username=os.environ["DEMO_USERNAME"],
            password_hash=os.environ["DEMO_PASSWORD_HASH"],
            owner_password_hash=os.environ.get("DEMO_OWNER_PASSWORD_HASH"),
            origins=tuple(x.strip() for x in os.environ["DEMO_ALLOWED_ORIGINS"].split(",") if x.strip()),
            ttl_minutes=int(os.environ.get("DEMO_TTL_MINUTES", "20")),
            conflict_policy=os.environ.get("DEMO_CONFLICT_POLICY", "wait_only"),
            secure_cookie=os.environ.get("DEMO_COOKIE_SECURE", "true") == "true",
        )
