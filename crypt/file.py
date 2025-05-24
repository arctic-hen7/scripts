#!/usr/bin/env python
# Opens the given GPG-encrypted file and runs a command on it, re-encrypting it every time the
# temporary file changes, and cleaning up properly on exit or error. The temporary plaintext file
# is written to `/dev/shm`, which should exist purely on RAM on most systems.
#
# Requirements
#   - `watchdog`

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Globals so the handler & signal handlers can see them
TEMP_DIR = None
PLAINTEXT_FILE = None
ENCRYPTED_FILE = None
RECIP_KEY = None
WATCHER = None
PROCESS = None
_ENCRYPT_LOCK = threading.Lock()

def debug(msg):
    print("[*]", msg, file=sys.stderr)

def parse_args():
    p = argparse.ArgumentParser(description="Edit a GPG‐encrypted file in /dev/shm")
    p.add_argument("encrypted", help="Path to .gpg encrypted file")
    p.add_argument("cmd", help="Command to run, use %FILE to refer to the plaintext file")
    return p.parse_args()

def decrypt_to_tmp(enc_path):
    """
    Decrypts enc_path to a temp file in /dev/shm, returning (tmpfile, recip_keyid).
    Uses --status-fd to pull out the ENC_TO line which contains the key ID.
    """
    tmpdir = tempfile.mkdtemp(prefix="gpg-edit", dir="/dev/shm")
    tmpfile = os.path.join(tmpdir, os.path.basename(enc_path).rstrip(".gpg"))
    cmd = [
        "gpg", "--batch", "--yes",
        "--status-fd", "2",
        "--decrypt",
        "--output", tmpfile,
        enc_path
    ]
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    _, stderr = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"GPG decryption failed: {proc.returncode}\n{stderr}")

    # Hunt for the key ID in status lines like "[GNUPG:] ENC_TO <keyid> ..."
    keyid = None
    for line in stderr.splitlines():
        if line.startswith("[GNUPG:] ENC_TO"):
            parts = line.split()
            # line format: [GNUPG:] ENC_TO ABCDEF0123456789 ...
            if len(parts) >= 2:
                keyid = parts[2]
                break
    if not keyid:
        raise RuntimeError("Could not determine recipient key ID from GPG status output.")

    return tmpdir, tmpfile, keyid

def encrypt_back(tmpfile, enc_path, keyid):
    """
    Encrypts tmpfile back to enc_path, to recipient keyid.
    """
    with _ENCRYPT_LOCK:
        cmd = [
            "gpg", "--batch", "--yes",
            # "--trust-model", "always",
            "--output", enc_path,
            "--recipient", keyid,
            "--encrypt",
            tmpfile
        ]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"GPG encryption failed with status code {r.returncode}:\n{r.stderr}")
        except Exception as e:
            raise RuntimeError(f"GPG encryption failed: {e}")

class ChangeHandler(FileSystemEventHandler):
    def __init__(self, plaintext, encrypted, keyid):
        super().__init__()
        self.plaintext = plaintext
        self.encrypted = encrypted
        self.keyid = keyid

    def on_modified(self, event):
        if event.src_path == self.plaintext:
            try:
                encrypt_back(self.plaintext, self.encrypted, self.keyid)
            except RuntimeError as e:
                # Just log the error, this is only an automatic re-encryption so not critical
                print(f"Automatic re-encryption failed: {e}", file=sys.stderr)

def cleanup_and_exit(_signum=None, _frame=None):
    # We're cleaning up, the child process won't be able to access the file, so kill it
    if PROCESS and PROCESS.poll() is None:
        print("Terminating child process...", file=sys.stderr)
        try:
            PROCESS.terminate()
        except Exception:
            pass

    # Re-encrypt
    try:
        encrypt_back(PLAINTEXT_FILE, ENCRYPTED_FILE, RECIP_KEY)
    except Exception as e:
        # If we hit this, the previous automatic re-encryptions likely failed too, and we're
        # about to lose data. Pause here and let the user manually resolve.
        print(f"[ERROR]: Cleanup encryption failed: {e}", file=sys.stderr)
        print()
        print(f"Please manually re-encrypt {PLAINTEXT_FILE} as you wish, and then press Enter to terminate this script. Otherwise, you will amost certainly LOSE DATA.", file=sys.stderr)
        input("Press Enter to continue...")

    # Stop the watcher and remove the temporary directory
    if WATCHER:
        WATCHER.stop()
        WATCHER.join()
    if TEMP_DIR and os.path.isdir(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    sys.exit(0 if (PROCESS and PROCESS.returncode in (0, None)) else 1)

def main():
    global TEMP_DIR, PLAINTEXT_FILE, ENCRYPTED_FILE, RECIP_KEY, WATCHER, PROCESS

    args = parse_args()
    if not args.cmd:
        print("Error: you must provide a command to run (with %FILE in it).", file=sys.stderr)
        sys.exit(1)

    ENCRYPTED_FILE = os.path.abspath(args.encrypted)
    if not os.path.exists(ENCRYPTED_FILE):
        print("Error: encrypted file does not exist:", ENCRYPTED_FILE, file=sys.stderr)
        sys.exit(1)

    # Decrypt and extract the key
    TEMP_DIR, PLAINTEXT_FILE, RECIP_KEY = decrypt_to_tmp(ENCRYPTED_FILE)

    # Signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, cleanup_and_exit)

    # Start filesystem watcher to re-encrypt on change
    handler = ChangeHandler(PLAINTEXT_FILE, ENCRYPTED_FILE, RECIP_KEY)
    WATCHER = Observer()
    WATCHER.schedule(handler, path=PLAINTEXT_FILE, recursive=False)
    WATCHER.start()

    # Run the user's command
    cmd = args.cmd.replace("%FILE", PLAINTEXT_FILE)
    try:
        PROCESS = subprocess.Popen(cmd, shell=True, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr)
        PROCESS.wait()
    except Exception as e:
        print(f"Error running command: {e}", file=sys.stderr)

    # Clean up and exit
    cleanup_and_exit()

if __name__ == "__main__":
    main()
