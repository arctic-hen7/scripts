#!/usr/bin/env python
# Processes journal entry information in the inbox for the given date. This expects both a
# typed/spoken entry for the journal itself, and a typed/spoken entry for the additional
# gratitude journal and goals for the next day.
#
# Requirements:
#   - $ACE_INBOX_DIR
#   - $ACE_JOURNALS_DIR: the directory containing daily journal files
#   - `openai`
#   - `send2trash`

from openai import OpenAI
import whisper
from pathlib import Path
import sys
import os
import subprocess
from send2trash import send2trash

client = OpenAI()
SELF_DIR = os.path.dirname(os.path.abspath(__file__))
ACE_INBOX_DIR = Path(os.getenv("ACE_INBOX_DIR"))
ALLOWED_AUDIO_EXTENSIONS = ['.mp4', '.m4a', '.wav', '.mp3']

ITEMS_INFERENCE_INSTRUCTIONS = """You will be given a transcription of a user describing entries in a gratitude journal, and goals for the next day. You should produce ONLY a Markdown-formatted output of the form:

# Gratitude Journal

1. <item-1>
2. <item-1>
(etc.)

# Goals for Tomorrow

- <goal-1>
- <goal-2>
(etc.)

Include no other text, and only the items the user has specified, using as much of their original language as possible, but use common sense to make them able to stand on their own (e.g. capitalise the first letter, add punctuation). Also, do *not* put blank lines between items. Your role is simply to structure their input."""

def transcribe_local(path):
    """
    Transcribes the given audio file with Whisper, using a local model (this could take a long
    time, but is suitable for private data).
    """
    model = whisper.load_model("turbo")
    result = model.transcribe(f"{path}")
    return result["text"]

def transcribe_cloud(path):
    """
    Transcribes the given audio file with Whisper, using the OpenAI API. This is faster, but
    exposes potentially sensitive data, so should be used with care for something like a daily
    journal.
    """
    # Use OpenAI Whisper to transcribe the file
    response = client.audio.transcriptions.create(
        model="whisper-1",
        file=open(path, 'rb')
    )
    return response.text

def infer_from_items(text):
    """
    Infers the structure of the journal's additional items from the given text (specifically
    a gratitude journal and goals for the next day). This is designed to be called on either
    a transcription of freeform audio describing these items, or on typed text. In the latter
    case, if the structure is obvious, this will extract the items without any AI.

    Otherwise, this uses `gpt-4.1-nano`, so should not contain any sensitive information.
    """
    # If the text starts with "# Gratitude Journal", we assume it's already structured
    if text.startswith("# Gratitude Journal"):
        return text
    else:
        response = client.responses.create(
            model="gpt-4.1-nano",
            instructions=ITEMS_INFERENCE_INSTRUCTIONS,
            input=text
        )
        return response.output_text

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Process journal entries for a given date.")
    parser.add_argument("journal_date", type=str, help="The date of the journal entry to process (YYYY-MM-DD).")
    parser.add_argument("--items-only", action="store_true",
                        help="Only process the additional items, not the main journal entry.")
    parser.add_argument("--journal-only", action="store_true", 
                        help="Only process the main journal entry, not the additional items.")
    args = parser.parse_args()

    journal_date = args.journal_date
    do_journal = args.journal_only or not args.items_only
    do_items = args.items_only or not args.journal_only

    trashes = []
    # We will have either a recording, or a typed entry, in the inbox, for both the journal proper
    # and the additional items (gratitude journal and goals)
    journal_text = None
    if do_journal:
        typed_journal_path = ACE_INBOX_DIR / f"journal_{journal_date}.md"
        if typed_journal_path.exists():
            # If we have a typed journal entry, we can just read it directly
            with open(typed_journal_path, 'r', encoding='utf-8') as file:
                journal_text = file.read()
                trashes.append(typed_journal_path)
        else:
            recording_path = None
            for ext in ALLOWED_AUDIO_EXTENSIONS:
                try_recording_path = ACE_INBOX_DIR / f"journal_{journal_date}{ext}"
                if try_recording_path.exists():
                    recording_path = try_recording_path
                    break
            if recording_path:
                # We found the recording, transcribe it *locally* (sensitive)
                print(f"Transcribing recording locally for {journal_date}...")
                text = transcribe_local(recording_path)
                if not text:
                    print(f"Error: transcription failed for {journal_date}.")
                else:
                    journal_text = text
                    trashes.append(recording_path)
            else:
                # No recording path, and no typed path
                print(f"Error: no journal found in the inbox for {journal_date}.")

    # Now do the additional items
    additional_items_text = None
    if do_items:
        typed_items_path = ACE_INBOX_DIR / f"items_{journal_date}.md"
        if typed_items_path.exists():
            # If we have a typed items entry, we can just read it directly
            with open(typed_items_path, 'r', encoding='utf-8') as file:
                additional_items_text = file.read()
                trashes.append(typed_items_path)
        else:
            recording_path = None
            for ext in ALLOWED_AUDIO_EXTENSIONS:
                try_recording_path = ACE_INBOX_DIR / f"items_{journal_date}{ext}"
                if try_recording_path.exists():
                    recording_path = try_recording_path
                    break
            if recording_path:
                # We found the recording, transcribe it *remotely* (less sensitive)
                print(f"Transcribing additional items recording remotely for {journal_date}...")
                text = transcribe_cloud(recording_path)
                if not text:
                    print(f"Error: transcription failed for additional items on {journal_date}.")
                else:
                    additional_items_text = text
                    trashes.append(recording_path)
            else:
                # No recording path, and no typed path
                print(f"Error: no additional items found in the inbox for {journal_date}.")

    # Now infer the structure of the additional items (if we have them)
    additional_items_text = infer_from_items(additional_items_text.strip()) if additional_items_text else None

    # Create the journal with our script
    create_result = subprocess.run(["bash", f"{SELF_DIR}/../journal/create.sh", journal_date], check=True, capture_output=True)
    # Path to the journal file is the last line of stdout
    journal_path = create_result.stdout.decode().strip().splitlines()[-1]

    # Replace the placeholders in the journal with our transcriptions
    with open(journal_path, 'r+', encoding='utf-8') as journal_file:
        content = journal_file.read()
        # First the actual journal
        if journal_text:
            content = content.replace("PLACEHOLDER\n\n# Gratitude Journal", f"{journal_text}\n\n# Gratitude Journal")
        # Then the additionals (more complex, Starling IDs get involved...)
        if additional_items_text:
            section_start = None
            section_end = None
            curr_section = None
            force_fail = False
            for i, line in enumerate(content.splitlines()):
                if not curr_section and line.startswith("# Gratitude Journal"):
                    section_start = i
                    curr_section = "gratitude"
                    continue
                elif curr_section == "gratitude" and line.startswith("# Goals for Tomorrow"):
                    curr_section = "goals"
                    continue
                elif curr_section == "goals" and line.startswith("# "):
                    # We may have reached an additional Sunday section
                    section_end = i - 1
                    break
                elif not curr_section:
                    # We're before the part we need, keep going
                    continue

                empties = ["1.", "2.", "3.", "-", "<!--PROPERTIES", "-->"]
                if line and line not in empties and not line.startswith("ID: "):
                    print(line)
                    # We've found a line with data, abort
                    print(f"Error: unexpected content in journal file for {journal_date}, not replacing additionals.")
                    trashes.clear()
                    force_fail = True
                    break

            if not force_fail:
                if section_start is None:
                    print(f"Error: could not find gratitude journal section in {journal_path}.")
                    trashes.clear()
                else:
                    content_lines = content.splitlines()
                    items_lines = additional_items_text.splitlines()
                    if section_end is None:
                        new_content_lines = content_lines[:section_start] + items_lines
                    else:
                        new_content_lines = content_lines[:section_start] + items_lines + content_lines[section_end + 1:]

                    # TODO: Need to make sure this works on Sundays...
                    content = "\n".join(new_content_lines)

        journal_file.seek(0)
        journal_file.write(content)
        journal_file.truncate()

    # Now trash the original files
    for f in trashes:
        send2trash(f)

    print(f"Inbox entries for {journal_date} added to {journal_path}.")

if __name__ == "__main__":
    main()
