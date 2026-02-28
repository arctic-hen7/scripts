#!/usr/bin/env python3
"""
Deep Research CLI - Manage Google Gemini Deep Research sessions

Usage:
  deep_research.py                      # Start new research (interactive)
  deep_research.py --editor             # Start with editor
  deep_research.py --session-id ID      # Start with custom session ID
  deep_research.py --list               # List all sessions
  deep_research.py --status SESSION_ID  # Check session status
  deep_research.py --resume SESSION_ID  # Resume/check existing session
  echo "prompt" | deep_research.py      # Start with stdin prompt

Environment:
  GEMINI_API_KEY - Required for API authentication
  EDITOR - Preferred editor for --editor flag (default: vi)
"""

import sys
import os
import json
import argparse
import time
import tempfile
import subprocess
import select
import re
import urllib.request
import urllib.error
import concurrent.futures
from pathlib import Path
from datetime import datetime


class SessionManager:
    """Manages session state persistence in cache directory"""

    def __init__(self, cache_dir=None):
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # XDG-compliant cache directory
            xdg_cache = os.environ.get('XDG_CACHE_HOME',
                                      os.path.expanduser('~/.cache'))
            self.cache_dir = Path(xdg_cache) / 'deep-research'

        self.sessions_dir = self.cache_dir / 'sessions'
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def generate_session_id(self, prompt, api_key):
        """Generate session ID using gemini-3-flash-preview"""
        try:
            from google import genai

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model='gemini-3-flash-preview',
                contents=f"Generate a short, lowercase, hyphen-separated identifier "
                        f"(3-5 words max) that captures the essence of this research topic: "
                        f"{prompt[:200]}. Respond with only the identifier, no explanation."
            )

            session_id = response.text.strip().lower()
            # Clean up the ID
            session_id = ''.join(c if c.isalnum() or c == '-' else '-'
                               for c in session_id)
            session_id = '-'.join(filter(None, session_id.split('-')))

            # Fallback if generation produces something invalid
            if not session_id or len(session_id) > 100:
                raise ValueError("Invalid generated ID")

            return session_id
        except Exception as e:
            # Fallback to timestamp-based ID
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            return f"research-{timestamp}"

    def create_session(self, prompt, interaction_id, session_id=None):
        """Create a new session state file"""
        if not session_id:
            raise ValueError("session_id is required")

        state = {
            'id': interaction_id,
            'status': 'in_progress',
            'prompt': prompt,
            'created_at': datetime.now().isoformat(),
            'session_id': session_id
        }

        self.save_session(session_id, state)
        return state

    def load_session(self, session_id):
        """Load session state from file"""
        state_file = self.sessions_dir / f"{session_id}.state.json"

        if not state_file.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found")

        with open(state_file, 'r') as f:
            return json.load(f)

    def save_session(self, session_id, state):
        """Save session state to file"""
        state_file = self.sessions_dir / f"{session_id}.state.json"

        with open(state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def list_sessions(self):
        """List all sessions with their status"""
        sessions = []

        for state_file in self.sessions_dir.glob('*.state.json'):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    sessions.append({
                        'session_id': state.get('session_id', state_file.stem.replace('.state', '')),
                        'status': state.get('status', 'unknown'),
                        'created_at': state.get('created_at', 'unknown'),
                        'prompt': state.get('prompt', '')[:80] + ('...' if len(state.get('prompt', '')) > 80 else '')
                    })
            except Exception:
                continue

        # Sort by creation time, newest first
        sessions.sort(key=lambda x: x['created_at'], reverse=True)
        return sessions


class DeepResearch:
    """Handles Deep Research API interactions"""

    def __init__(self, api_key):
        from google import genai
        self.client = genai.Client(api_key=api_key)

    def start_research_stream(self, prompt):
        """Start a new deep research task with streaming"""
        stream = self.client.interactions.create(
            input=prompt,
            agent='deep-research-pro-preview-12-2025',
            background=True,
            stream=True,
            agent_config={
                'type': 'deep-research',
                'thinking_summaries': 'auto'
            }
        )
        return stream

    def resume_stream(self, interaction_id):
        """Resume streaming for an existing interaction (from beginning)"""
        stream = self.client.interactions.get(
            interaction_id,
            stream=True
        )
        return stream

    def stream_interaction(self, stream):
        """Process stream and return completed interaction"""
        interaction_id = None
        print()  # New line before streaming output

        try:
            for chunk in stream:
                # Capture interaction ID on start
                if chunk.event_type == "interaction.start":
                    interaction_id = chunk.interaction.id

                # Handle content deltas
                elif chunk.event_type == "content.delta":
                    if chunk.delta.type == "text":
                        print(chunk.delta.text, end="", flush=True)
                    elif chunk.delta.type == "thought_summary":
                        thought_text = chunk.delta.content.text if hasattr(chunk.delta.content, 'text') else str(chunk.delta.content)
                        print(f"\n[Thought: {thought_text}]", flush=True)

                # Handle completion
                elif chunk.event_type == "interaction.complete":
                    print("\n")
                    if interaction_id:
                        return self.client.interactions.get(interaction_id)

            # Stream ended - fetch final state
            if interaction_id:
                return self.client.interactions.get(interaction_id)

            raise Exception("Stream ended without completion")

        except Exception as e:
            if interaction_id:
                try:
                    return self.client.interactions.get(interaction_id)
                except:
                    pass
            raise e

    def get_status(self, interaction_id):
        """Get current status of an interaction"""
        interaction = self.client.interactions.get(interaction_id)
        return {
            'id': interaction.id,
            'status': interaction.status,
            'has_outputs': hasattr(interaction, 'outputs') and interaction.outputs
        }


def get_prompt_from_stdin():
    """Check if there's input available on stdin"""
    # Check if stdin is a pipe or redirect (not a tty)
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    return None


def get_prompt_from_editor():
    """Open user's preferred editor to get prompt"""
    editor = os.environ.get('EDITOR', 'vi')

    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as tf:
        temp_path = tf.name
        tf.write("# Enter your research prompt below\n")
        tf.write("# Lines starting with # will be ignored\n\n")

    try:
        subprocess.run([editor, temp_path], check=True)

        with open(temp_path, 'r') as f:
            lines = [line for line in f.readlines()
                    if not line.strip().startswith('#')]
            prompt = ''.join(lines).strip()

        return prompt
    finally:
        os.unlink(temp_path)


def get_prompt_interactive():
    """Get multi-line prompt from interactive input"""
    print("Enter your research prompt (Ctrl+D or type 'END' on a new line to finish):")
    print()

    lines = []
    try:
        while True:
            line = input()
            if line.strip() == 'END':
                break
            lines.append(line)
    except EOFError:
        pass

    return '\n'.join(lines).strip()


def get_prompt(use_editor=False):
    """Get research prompt from various sources"""
    # Priority 1: stdin
    prompt = get_prompt_from_stdin()
    if prompt:
        return prompt

    # Priority 2: editor
    if use_editor:
        return get_prompt_from_editor()

    # Priority 3: interactive
    return get_prompt_interactive()


def parse_citations(markdown_text):
    """Parse and convert citations from [cite: X] format to proper Markdown links"""
    if not markdown_text:
        return markdown_text

    # Extract and resolve URLs
    url_pattern = re.compile(r'https?://[^\s<>\[\]()]+')
    urls = list(dict.fromkeys(url_pattern.findall(markdown_text)))

    if urls:
        print(f"Resolving {len(urls)} URLs...", flush=True)
        resolved_urls = resolve_urls_in_parallel(urls)
        for original, resolved in resolved_urls.items():
            if resolved and resolved != original:
                markdown_text = markdown_text.replace(original, resolved)

    # Find the Sources section
    sources_match = re.search(r'\*\*Sources:\*\*\s*\n', markdown_text, re.IGNORECASE)
    if not sources_match:
        return markdown_text

    sources_start = sources_match.end()
    content = markdown_text[:sources_start]
    sources = markdown_text[sources_start:]

    # Add anchors to numbered sources (e.g., "1. " -> "<a name='cite1'></a>1. ")
    sources = re.sub(
        r'^(\d+)\. ',
        lambda m: f'<a name="cite{m.group(1)}"></a>{m.group(1)}. ',
        sources,
        flags=re.MULTILINE
    )

    # Convert [cite: X] or [cite: X, Y, Z] to proper links
    content = re.sub(
        r'\[cite:\s*([0-9,\s]+)\]',
        lambda m: ', '.join(f'[{n.strip()}](#cite{n.strip()})' for n in m.group(1).split(',')),
        content,
        flags=re.IGNORECASE
    )

    return content + sources


def resolve_urls_in_parallel(urls, timeout=15):
    """Resolve URLs in parallel to handle redirects efficiently"""
    if not urls:
        return {}

    max_workers = min(16, len(urls))
    resolved = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(resolve_url, url, timeout): url for url in urls}
        for future in concurrent.futures.as_completed(future_map):
            original = future_map[future]
            try:
                resolved_url = future.result()
                resolved[original] = resolved_url or original
            except Exception:
                resolved[original] = original

    return resolved


def resolve_url(url, timeout=15):
    """Resolve URL redirects, particularly for Vertex AI grounding redirect URLs"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    # Try GET first for redirect URLs (more reliable)
    for method in ('GET', 'HEAD'):
        try:
            request = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                # Read a small amount to ensure the request completes
                if method == 'GET':
                    response.read(512)
                return response.geturl()
        except urllib.error.HTTPError as e:
            # If we get a redirect error, try to extract the location
            if e.headers and 'Location' in e.headers:
                return e.headers['Location']
            continue
        except (urllib.error.URLError, ValueError, OSError):
            continue

    return url


def ensure_blank_line_before_bullets(markdown_text):
    """Ensure proper spacing before bullet lists for better markdown rendering"""
    if not markdown_text:
        return markdown_text

    lines = markdown_text.splitlines()
    updated_lines = []
    in_code_block = False

    for line in lines:
        # Track code blocks to avoid modifying their content
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            updated_lines.append(line)
            continue

        if in_code_block:
            updated_lines.append(line)
            continue

        # Add blank line before bullet if previous line has content and isn't a bullet
        if is_bullet_line(line) and updated_lines:
            prev_line = updated_lines[-1]
            if prev_line.strip() and not is_bullet_line(prev_line):
                updated_lines.append("")

        updated_lines.append(line)

    return "\n".join(updated_lines)


def is_bullet_line(line):
    """Check if a line is a bullet point, handling blockquotes"""
    trimmed = line.lstrip()
    # Strip blockquote markers
    while trimmed.startswith(">"):
        trimmed = trimmed[1:].lstrip()
    return bool(re.match(r'^[-*+]\s+', trimmed))


def save_outputs(session_id, interaction):
    """Save interaction outputs to Markdown file with parsed citations"""
    # Extract text from outputs
    if not hasattr(interaction, 'outputs') or not interaction.outputs:
        print("\nWarning: No outputs found in interaction", file=sys.stderr)
        return

    markdown_text = getattr(interaction.outputs[-1], 'text', None)
    if not markdown_text:
        print("\nWarning: No text output found in interaction", file=sys.stderr)
        return

    # Parse citations and format
    parsed_markdown = parse_citations(markdown_text)
    parsed_markdown = ensure_blank_line_before_bullets(parsed_markdown)

    # Save Markdown content
    md_path = Path(f"{session_id}.md")
    with open(md_path, 'w') as f:
        f.write(parsed_markdown)

    print(f"\nMarkdown report saved to: {md_path}")


def format_duration(seconds):
    """Format duration in human-readable format"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds / 3600)
        mins = int((seconds % 3600) / 60)
        return f"{hours}h {mins}m"


def main():
    parser = argparse.ArgumentParser(
        description='Deep Research CLI - Manage Google Gemini Deep Research sessions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('--session-id', help='Custom session ID')
    parser.add_argument('--editor', action='store_true',
                       help='Open editor to enter prompt')
    parser.add_argument('--list', action='store_true',
                       help='List all sessions')
    parser.add_argument('--status', metavar='SESSION_ID',
                       help='Check status of a session')
    parser.add_argument('--resume', metavar='SESSION_ID',
                       help='Resume/check existing session')
    parser.add_argument('--cache-dir',
                       help='Custom cache directory (default: ~/.cache/deep-research)')

    args = parser.parse_args()

    # Initialize session manager
    session_mgr = SessionManager(args.cache_dir)

    # Handle list command
    if args.list:
        sessions = session_mgr.list_sessions()
        if not sessions:
            print("No sessions found.")
            return

        print(f"\n{'SESSION ID':<30} {'STATUS':<12} {'CREATED':<20} {'PROMPT'}")
        print("-" * 120)
        for s in sessions:
            print(f"{s['session_id']:<30} {s['status']:<12} {s['created_at']:<20} {s['prompt']}")
        print()
        return

    # Check API key
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set", file=sys.stderr)
        sys.exit(1)

    research = DeepResearch(api_key)

    # Handle status command
    if args.status:
        try:
            state = session_mgr.load_session(args.status)
            status = research.get_status(state['id'])

            print(f"\nSession: {args.status}")
            print(f"Status: {status['status']}")
            print(f"Interaction ID: {status['id']}")
            print(f"Created: {state['created_at']}")
            print(f"Prompt: {state['prompt'][:200]}...")

            if status['status'] == 'completed':
                print(f"\nOutput available: Check {args.status}.md")

        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error checking status: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Handle resume command
    if args.resume:
        try:
            state = session_mgr.load_session(args.resume)
            interaction_id = state['id']
            session_id = state['session_id']

            print(f"\nResuming session: {session_id}")
            print(f"Prompt: {state['prompt'][:200]}...")
            print(f"\nChecking status...")

            status = research.get_status(interaction_id)

            if status['status'] == 'completed':
                print(f"Status: completed")
                print("\nFetching results...")
                interaction = research.client.interactions.get(interaction_id)
                save_outputs(session_id, interaction)

                # Update state
                state['status'] = 'completed'
                session_mgr.save_session(session_id, state)
                return

            elif status['status'] == 'failed':
                print(f"Status: failed")
                state['status'] = 'failed'
                session_mgr.save_session(session_id, state)
                return

            # Still in progress, resume streaming from beginning
            print(f"Status: {status['status']}")
            print("Resuming stream (Ctrl+C to stop)...")

            start_time = time.time()

            try:
                # Resume stream from beginning (no last_event_id)
                stream = research.resume_stream(interaction_id)
                interaction = research.stream_interaction(stream)

                elapsed = time.time() - start_time
                print(f"Research completed in {format_duration(elapsed)}!")

                save_outputs(session_id, interaction)

                # Update state
                state['status'] = 'completed'
                session_mgr.save_session(session_id, state)

            except KeyboardInterrupt:
                print("\n\nInterrupted. Session state saved. Resume with: --resume", session_id)
                sys.exit(0)
            except Exception as e:
                print(f"\nError: {e}", file=sys.stderr)
                state['status'] = 'failed'
                state['error'] = str(e)
                session_mgr.save_session(session_id, state)
                sys.exit(1)

        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # Default: Start new research
    try:
        # Get prompt
        prompt = get_prompt(args.editor)

        if not prompt:
            print("Error: No prompt provided", file=sys.stderr)
            sys.exit(1)

        print("\nGenerating session ID...")

        # Generate or use provided session ID
        if args.session_id:
            session_id = args.session_id
        else:
            session_id = session_mgr.generate_session_id(prompt, api_key)

        print(f"Session ID: {session_id}")
        print(f"\nStarting deep research...")
        print(f"Prompt: {prompt[:200]}{'...' if len(prompt) > 200 else ''}\n")

        start_time = time.time()

        try:
            # Start research with streaming
            stream = research.start_research_stream(prompt)

            # Process stream and save session on first chunk
            interaction_id = None
            print()

            for chunk in stream:
                # Capture interaction ID and create session
                if chunk.event_type == "interaction.start":
                    interaction_id = chunk.interaction.id
                    session_mgr.create_session(prompt, interaction_id, session_id)
                    print(f"[Research started. Interaction ID: {interaction_id}]")

                # Stream content
                elif chunk.event_type == "content.delta":
                    if chunk.delta.type == "text":
                        print(chunk.delta.text, end="", flush=True)
                    elif chunk.delta.type == "thought_summary":
                        thought_text = chunk.delta.content.text if hasattr(chunk.delta.content, 'text') else str(chunk.delta.content)
                        print(f"\n[Thought: {thought_text}]", flush=True)

                elif chunk.event_type == "interaction.complete":
                    print("\n")
                    break

            # Get final interaction state
            if not interaction_id:
                raise Exception("Failed to get interaction ID from stream")

            interaction = research.client.interactions.get(interaction_id)
            elapsed = time.time() - start_time
            print(f"Research completed in {format_duration(elapsed)}!")

            save_outputs(session_id, interaction)

            # Update state
            state = session_mgr.load_session(session_id)
            state['status'] = 'completed'
            session_mgr.save_session(session_id, state)

        except KeyboardInterrupt:
            print(f"\n\nInterrupted. Session state saved.")
            print(f"Resume with: python {sys.argv[0]} --resume {session_id}")
            sys.exit(0)
        except Exception as e:
            print(f"\nError: {e}", file=sys.stderr)

            # Try to update state if session was created
            try:
                state = session_mgr.load_session(session_id)
                state['status'] = 'failed'
                state['error'] = str(e)
                session_mgr.save_session(session_id, state)
            except:
                pass
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
