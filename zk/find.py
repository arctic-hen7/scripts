#!/usr/bin/env python3
# Searches for a node in the system by its title and opens it. Technically, this will
# search across the whole of a Starling instance, so it's not just limited to Zettelkasten
# nodes.
#
# Requirements:
#   - fzf
#   - curl
#   - nvim
#   - $ACE_ZK_DIR

import subprocess
import json
import os
import sys

STARLING_ADDR = "http://localhost:3000"
ACE_MAIN_DIR = os.getenv("ACE_MAIN_DIR")

curl_command = f"curl --connect-timeout 1 --max-time 10 -s -X GET '{STARLING_ADDR}/nodes' -H \"Content-Type: application/json\" -d '{{\"conn_format\": \"markdown\"}}\'"

def get_nodes():
    """Fetch nodes from the server and parse them as JSON."""

    try:
        result = subprocess.check_output(curl_command, shell=True)
        nodes = json.loads(result)
        return nodes
    except subprocess.CalledProcessError as e:
        print(f"Error calling curl: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}", file=sys.stderr)
        sys.exit(1)

def combine_titles(nodes):
    """Combine titles into a one-liner string."""

    return [" / ".join(node["title"]) for node in nodes]

def fuzzy_find(options):
    """Use fzf to allow the user to select an option."""

    fzf_process = subprocess.Popen(
        ["fzf", "--height=10"], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    option_input = "\n".join(options).encode("utf-8")
    stdout_data, _ = fzf_process.communicate(input=option_input)

    if fzf_process.returncode != 0:
        print("No selection made", file=sys.stderr)
        sys.exit(1)

    return stdout_data.decode("utf-8").strip()

def main(path_scope):
    nodes = get_nodes()
    if path_scope is not None:
        nodes = {"/".join(node["title"]): node for node in nodes if node["path"].startswith(path_scope)}
    else:
        nodes = {"/".join(node["title"]): node for node in nodes}
    selected_title = fuzzy_find(nodes.keys())

    # Find the corresponding node
    selected_node = nodes.get(selected_title)
    if selected_node is None:
        print("Selected title not found in nodes", file=sys.stderr)
        sys.exit(1)

    path = selected_node["path"]

    # Open the path in nvim
    full_path = os.path.join(ACE_MAIN_DIR, path)
    subprocess.run(["nvim", full_path])

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Find a node in the system by its title and open it.")
    parser.add_argument("path_scope", nargs="?", help="Path scope to search within")
    args = parser.parse_args()

    main(args.path_scope)
