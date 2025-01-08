#!/usr/bin/env python3

import os
import uuid
import concurrent.futures
from openai import OpenAI
import shutil

ACE_INBOX_DIR = os.getenv('ACE_INBOX_DIR')
client = OpenAI()

def transcribe_mp4(mp4_path):
    """
    Transcribes the given mp4 file with Whisper.
    """
    try:
        # Use OpenAI Whisper to transcribe the file
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=open(mp4_path, 'rb')
        )
        return response.text
    except Exception as e:
        print(f"Failed to transcribe {mp4_path}: {e}")
        return None

def process_bundle(bundle_path):
    """
    Processes the given capture bundle, skipping it if it contains a `.processed` file, and warning
    if there are any unhandled attachments. For new bundles, a `HEARME.mp4` file will be
    transcribed with Whisper and the result will be written to a `README.md` file.
    """

    # Skip processing if there's already a .processed file
    if '.processed' in os.listdir(bundle_path):
        attachments = [f for f in os.listdir(bundle_path) if f not in ('.processed', 'README.md', 'HEARME.mp4')]
        if attachments:
            print(f"Warning: Bundle with un-handled attachments: {bundle_path}")
        elif len(attachments) == 0:
            shutil.rmtree(bundle_path)
        return False

    readme_path = os.path.join(bundle_path, 'README.md')
    hearme_path = os.path.join(bundle_path, 'HEARME.mp4')

    if os.path.exists(hearme_path):
        transcription = transcribe_mp4(hearme_path)
        if transcription:
            with open(readme_path, 'w') as f:
                f.write(transcription)

    return True

def update_review(bundle_path):
    """
    Adds the `README.md` in the given bundle to the `review.md` file, along with links to all
    atatchments in the bundle so the user can process them all in one place.
    """
    readme_path = os.path.join(bundle_path, 'README.md')
    review_file = os.path.join(ACE_INBOX_DIR, 'review.md')

    with open(readme_path, 'r') as f:
        contents = f.read()

    contents = f"# {contents}"

    links = []
    for root, _, files in os.walk(bundle_path):
        for file in files:
            if file not in ('README.md', 'HEARME.mp4'):
                rel_path = os.path.relpath(os.path.join(root, file), ACE_INBOX_DIR)
                links.append(f"- [{file}]({rel_path})")

    with open(review_file, 'a') as review:
        entry = f"{contents}\n" + "\n".join(links)
        if not os.path.exists(review_file) or os.path.getsize(review_file) == 0:
            review.write(entry.strip())
        else:
            review.write("\n\n" + entry.strip())

    # Mark as processed
    open(os.path.join(bundle_path, '.processed'), 'a').close()

def main():
    bundles = [
        os.path.join(ACE_INBOX_DIR, d) for d in os.listdir(ACE_INBOX_DIR)
        if os.path.isdir(os.path.join(ACE_INBOX_DIR, d)) and
            # Checking for a valid UUID prevents checking the `next/` folder
           uuid.UUID(d, version=4)
    ]

    processed_bundles = []

    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(process_bundle, bundles)
        processed_bundles = [bundle for bundle, processed in zip(bundles, results) if processed]

    for bundle in processed_bundles:
        update_review(bundle)

if __name__ == "__main__":
    main()
