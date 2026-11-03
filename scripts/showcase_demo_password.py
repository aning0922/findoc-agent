"""Read an operator password privately and emit only its deployment hash."""
from getpass import getpass

from app.demo.config import password_hash


if __name__ == "__main__":
    password = getpass("Password to hash: ")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters")
    print(password_hash(password))
