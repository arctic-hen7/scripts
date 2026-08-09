#!/usr/bin/env python

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from telethon.sync import TelegramClient


# ---------------------------------------------------------------------------
# Configuration: replace these values.
# ---------------------------------------------------------------------------

API_ID = int(os.environ["TUESDAY_API_ID"])
API_HASH = os.environ["TUESDAY_API_HASH"]
BOT_USERNAME = os.environ["TUESDAY_BOT_ID"]

# This is intentionally a hardcoded absolute path.
# Replace YOUR_USERNAME with your actual Linux username.
FAILED_CAPTURE_FILE = Path(os.environ["ACE_INBOX_DIR"]) / "failed.log"

# The session file is effectively a logged-in Telegram credential.
SESSION_FILE = Path.home() / ".local/share/tg-capture/user-session"


# Make newly created session and failure files private to this user.
os.umask(0o077)


def create_client() -> TelegramClient:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    return TelegramClient(
        str(SESSION_FILE),
        API_ID,
        API_HASH,
        timeout=10,
        connection_retries=1,
        request_retries=1,
        retry_delay=1,
        auto_reconnect=False,
        flood_sleep_threshold=0,
    )


def notify_failure(title: str, body: str) -> None:
    try:
        subprocess.run(
            [
                "notify-send",
                "--urgency=critical",
                "--app-name=Telegram Capture",
                title,
                body,
            ],
            check=False,
        )
    except OSError:
        # stderr will still contain the failure information.
        pass


def save_failed_capture(text: str, error: Exception) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")

    record = (
        "\n"
        "============================================================\n"
        f"FAILED TELEGRAM CAPTURE: {timestamp}\n"
        f"ERROR: {type(error).__name__}: {error}\n"
        "------------------------------------------------------------\n"
        f"{text}\n"
        "============================================================\n"
    )

    try:
        FAILED_CAPTURE_FILE.parent.mkdir(parents=True, exist_ok=True)

        # O_APPEND prevents an existing failure log from being overwritten.
        fd = os.open(
            FAILED_CAPTURE_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )

        with os.fdopen(fd, "a", encoding="utf-8") as file:
            file.write(record)
            file.flush()
            os.fsync(file.fileno())

    except Exception as save_error:
        print(
            "\nTELEGRAM SEND FAILED AND THE LOCAL FALLBACK ALSO FAILED.",
            file=sys.stderr,
        )
        print(f"Telegram error: {error}", file=sys.stderr)
        print(f"Local-file error: {save_error}", file=sys.stderr)
        print("\nUNSAVED CAPTURE:\n", file=sys.stderr)
        print(text, file=sys.stderr)

        notify_failure(
            "CAPTURE NOT SENT OR SAVED",
            "Telegram sending failed, and the local fallback file could not "
            "be written. Return to the capture terminal immediately.",
        )
        raise


def authenticate() -> int:
    client = create_client()

    try:
        # Interactive on the first run: phone number, login code, and
        # Telegram 2FA password where applicable.
        client.start()
        account = client.get_me()

        display_name = " ".join(
            part for part in (account.first_name, account.last_name) if part
        )

        print(f"Authenticated as {display_name or account.id}")

        if account.username:
            print(f"Username: @{account.username}")

        print(f"Session stored at: {SESSION_FILE}.session")
        return 0

    finally:
        if client.is_connected():
            client.disconnect()


def read_capture() -> str:
    if sys.stdin.isatty():
        return input("Capture: ").rstrip("\n")

    return sys.stdin.read().rstrip("\n")


def send_capture(text: str) -> int:
    client = create_client()

    try:
        client.start()

        message = client.send_message(
            BOT_USERNAME,
            text,
            parse_mode=None,
            link_preview=False,
        )

    except Exception as error:
        try:
            save_failed_capture(text, error)
        except Exception:
            return 2

        print(
            f"Telegram send failed. Capture saved to {FAILED_CAPTURE_FILE}",
            file=sys.stderr,
        )
        print(f"Reason: {type(error).__name__}: {error}", file=sys.stderr)

        notify_failure(
            "TELEGRAM CAPTURE NOT SENT",
            "The capture was NOT delivered to Telegram.\n\n"
            f"It has been saved locally at:\n{FAILED_CAPTURE_FILE}",
        )

        return 1

    finally:
        if client.is_connected():
            try:
                client.disconnect()
            except Exception:
                # send_message already returned successfully, so Telegram
                # accepted the message. A disconnect error does not make the
                # capture unsuccessful.
                pass

    print(f"Sent Telegram message {message.id}")
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--login":
        return authenticate()

    if len(sys.argv) > 1:
        print(f"Usage: {sys.argv[0]} [--login]", file=sys.stderr)
        return 64

    text = read_capture()

    if not text:
        print("Nothing captured.", file=sys.stderr)
        return 64

    return send_capture(text)


if __name__ == "__main__":
    raise SystemExit(main())

