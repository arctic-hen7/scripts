#!/usr/bin/env python3
# Manages an index of the Zettelkasten using Chroma. This directly requests documents from Starling
# and builds an index, including metadata, for semantic search.
#
# This will work with a cache (in $ACE_CACHE_DIR), which will store a JSON file to prevent re-
# indexing of unchanged content.
#
# Requirements:
#   - $ACE_CACHE_DIR
#   - $ACE_MAIN_DIR
#   - chroma

import chromadb
from chromadb.config import Settings
import os
import requests
import hashlib
import json
import inquirer
import subprocess

ACE_MAIN_DIR = os.getenv("ACE_MAIN_DIR")
ACE_CACHE_DIR = os.getenv("ACE_CACHE_DIR")
STARLING_ADDR = "http://localhost:3000" # YMMV
# This JSON file is a map of node ids to the hashes of their corresponding Starling objects
CACHE_PATH = os.path.join(ACE_CACHE_DIR, "zk_index_cache.json")

client = chromadb.PersistentClient(path=os.path.join(ACE_CACHE_DIR, "zk_index"), settings=Settings(anonymized_telemetry=False))
collection = client.get_or_create_collection(name="zk_index")

def get_nodes(path_scope):
    """
    Gets all nodes from Starling in files that match the given path scope.
    """

    response = requests.get(f"{STARLING_ADDR}/nodes", json={"conn_format": "markdown", "metadata": True, "body": True})
    if response.status_code == 200:
        nodes = response.json()
        if path_scope is not None:
            nodes = [node for node in nodes if node["path"].startswith(path_scope)]
        return nodes
    else:
        raise Exception(f"Failed to get action items: {response.text}")

def filter_nodes_to_changed(nodes):
    """
    Filters nodes to only those that have changed since the last index. This will return the new
    index for writing after indexing has been successful.
    """

    changed_nodes = []
    new_cached_nodes = {}
    removed_nodes = []

    # Read the cached list of node IDs
    if not os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "w") as f:
            f.write("{}")

    with open(CACHE_PATH, "r") as f:
        cached_nodes = json.load(f)

    for node in nodes:
        # Hash the node's data
        node_str = json.dumps(node, sort_keys=True)
        node_hash = hashlib.blake2b(node_str.encode()).hexdigest()

        if node["id"] not in cached_nodes or cached_nodes[node["id"]] != node_hash:
            changed_nodes.append(node)
            new_cached_nodes[node["id"]] = node_hash
        else:
            new_cached_nodes[node["id"]] = cached_nodes[node["id"]]
            del cached_nodes[node["id"]]

    # Check on any that have been removed
    for id in cached_nodes.keys():
        removed_nodes.append(id)

    return changed_nodes, new_cached_nodes, removed_nodes

def index_nodes(nodes):
    """
    Actually adds the given nodes to the index.
    """

    print(f"Need to update {nodes.__len__()} nodes.")
    if nodes.__len__() == 0:
        return

    collection.upsert(
        documents=[f"{'#' * (node['metadata']['level'] + 1)} {'/'.join(node['title'])}\n{node['body']}" for node in nodes],
        metadatas=[{"path": node["path"]} for node in nodes],
        ids=[node["id"] for node in nodes]
    )

def remove_nodes(ids):
    """
    Removes the given nodes from the index.
    """

    if len(ids) == 0:
        return
    collection.delete(ids=ids)

def update_index(path_scope):
    nodes = get_nodes(path_scope)
    changed_nodes, cached_nodes, removed_nodes = filter_nodes_to_changed(nodes)
    index_nodes(changed_nodes)
    remove_nodes(removed_nodes)

    # Write the new cache
    with open(CACHE_PATH, "w") as f:
        json.dump(cached_nodes, f)

def search_index(query, n_results, contains=None, not_contains=None):
    """
    Searches the index for the given query.
    """

    # Construct a where document from the contains and not_contains parameters
    where_document = {}
    if contains is not None:
        where_document["$contains"] = contains
    if not_contains is not None:
        where_document["$not_contains"] = not_contains

    # Allow the user to provide a query string, or array
    query_texts = []
    if isinstance(query, str):
        query_texts = [query]

    return collection.query(
        query_texts=query_texts,
        n_results=n_results,
        where_document=where_document,
    )

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build an index of the Zettelkasten using Chroma.")
    subparsers = parser.add_subparsers(dest="command")
    build_parser = subparsers.add_parser("build", help="Build the index")
    build_parser.add_argument("path_scope", nargs="?", help="Path scope to search within")
    search_parser = subparsers.add_parser("search", help="Search the index")
    search_parser.add_argument("query", help="Query to search for")
    search_parser.add_argument("-n", "--num-results", type=int, default=10, help="Number of results to return")
    search_parser.add_argument("--contains", help="Text that must be contained in the result")
    search_parser.add_argument("--not-contains", help="Text that must not be contained in the result")
    args = parser.parse_args()

    if args.command == "build":
        print("Updating index...")
        update_index(args.path_scope)
        print("Index updated!")
    elif args.command == "search":
        results = search_index(args.query, args.num_results, args.contains, args.not_contains)
        documents = results["documents"][0]
        paths = [metadata["path"] for metadata in results["metadatas"][0]]

        # The title of each document is on the first line, and we'll remove leading hashes
        titles = [doc.split("\n")[0].replace("#", "").strip() for doc in documents]

        # Let the user choose between the results and open their selected result's path
        question = [
            inquirer.List(
                "choice",
                message="Select a result to open",
                choices=titles
            )
        ]

        # Display the menu and get the user's choice
        answer = inquirer.prompt(question)

        if answer and "choice" in answer:
            # Find the path corresponding to the selected title
            selected_title = answer["choice"]
            selected_idx = titles.index(selected_title)
            selected_path = paths[selected_idx]

            # Use the path for whatever processing you require
            subprocess.run(["nvim", os.path.join(ACE_MAIN_DIR, selected_path)])
        else:
            print("No valid option selected.")

    else:
        print("Invalid command.")

if __name__ == "__main__":
    main()
