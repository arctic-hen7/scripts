#!/usr/bin/python3
# Script for managing Git repositories.
#
# Requirements:
#   - $ACE_REPOS_CONFIG: the path to the 'repos.toml' file
#   - $ACE_REPOS_DIR: the directory where repositories are stored
#   - pip::toml

import os
import subprocess
import sys
import toml
from pathlib import Path
import shutil

# Paths
CONFIG_PATH = os.environ["ACE_REPOS_CONFIG"]
CODE_DIR = Path(os.environ["ACE_REPOS_DIR"])

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        config = toml.load(f)
    if 'repos' not in config:
        config['repos'] = []
    return config

def save_config(config):
    with open(CONFIG_PATH, 'w') as f:
        toml.dump(config, f)

def run_git_command(repo_path, command):
    return subprocess.run(['git'] + command, cwd=repo_path, text=True, capture_output=True)

def get_status(repo_path, verbose=False):
    if not repo_path.exists():
        return 'not cloned', None

    status = run_git_command(repo_path, ['status', '--porcelain'])
    if status.returncode != 0:
        return 'error', status.stderr

    if verbose:
        full_status = run_git_command(repo_path, ['status']).stdout
    else:
        full_status = None

    if not status.stdout.strip():
        commits = run_git_command(repo_path, ['log', '@{u}..']).stdout.strip()
        return ('all good' if not commits else 'needs syncing'), full_status

    return 'needs commit', full_status

def status(repo_name=None):
    config = load_config()
    if repo_name:
        for repo in config['repos']:
            if repo['name'] == repo_name:
                repo_path = CODE_DIR / repo_name
                current_status, full_status = get_status(repo_path, verbose=True)
                print(f"{repo_name}: {current_status}")
                if full_status:
                    print(full_status)
                return
    else:
        for repo in config['repos']:
            repo_path = CODE_DIR / repo['name']
            current_status, _ = get_status(repo_path)
            print(f"{repo['name']}: {current_status}")

def find_orphans():
    config = load_config()
    known_repos = {repo['name'] for repo in config['repos']}
    origin_none_repos = [repo['name'] for repo in config['repos'] if repo['origin'] == 'NONE']

    print("Orphaned Repositories:")
    for repo_path in CODE_DIR.iterdir():
        if repo_path.is_dir() and (repo_path / '.git').exists():
            if repo_path.name not in known_repos:
                print(f"  {repo_path.name}")

    if origin_none_repos:
        print("\nRepositories with 'NONE' as origin:")
        for repo_name in origin_none_repos:
            print(f"  {repo_name}")

def get_repo(repo_name, repo_config):
    repo_path = CODE_DIR / repo_name
    if not repo_path.exists():
        print(f"Cloning {repo_name} into {CODE_DIR}")
        subprocess.run(['git', 'clone', repo_config['origin'], str(repo_path)])
    else:
        print(f"Repo {repo_name} already cloned. Skipping clone.")

    for hardlink in repo_config.get('hardlinks', []):
        setup_hardlink(repo_path, hardlink)

def get(repo_name=None):
    config = load_config()
    if repo_name:
        repo_config = next((repo for repo in config['repos'] if repo['name'] == repo_name), None)
        if repo_config:
            get_repo(repo_name, repo_config)
        else:
            print(f"Repo {repo_name} not found in config")
            sys.exit(1)
    else:
        for repo in config['repos']:
            if repo.get('needed', False):
                get_repo(repo['name'], repo)

def setup_hardlink(repo_path, hardlink):
    repopath, syspath = hardlink.split(':')
    source = repo_path / repopath
    syspath = Path(os.path.expandvars(syspath))

    if syspath.exists():
        if not syspath.samefile(source):
            print(f"Conflicting hardlink: {syspath} already exists and is not linked to {source}")
    else:
        os.link(source, syspath)
        print(f"Created hardlink from {source} to {syspath}")

def remove(repo_name, force=False):
    repo_path = CODE_DIR / repo_name
    current_status, _ = get_status(repo_path)

    if current_status == 'all good':
        shutil.rmtree(repo_path)
        print(f"Removed {repo_path}")
    elif force:
        confirm = input(f"Are you sure you want to forcefully remove {repo_path}? (y/N): ").strip().lower()
        if confirm == 'y':
            shutil.rmtree(repo_path)
            print(f"Forcefully removed {repo_path}")
        else:
            print("Operation cancelled.")
            sys.exit(1)
    else:
        print(f"Cannot remove {repo_path}: status is {current_status}. Use --force to override.")
        sys.exit(1)

def link(repo_name, hardlinks=None, needed=False):
    repo_path = CODE_DIR / repo_name
    result = run_git_command(repo_path, ['remote', 'get-url', 'origin'])
    if result.returncode != 0 and result.stderr.strip() == "error: No such remote 'origin'":
        origin_url = "NONE"
    elif result.returncode != 0:
        print(f"Error fetching origin: {result.stderr.strip()}")
        sys.exit(1)
    else:
        origin_url = result.stdout.strip()

    config = load_config()

    repo_config = next((repo for repo in config['repos'] if repo['name'] == repo_name), None)

    if repo_config:
        # Update existing repo entry (adding to hardlinks)
        repo_config['origin'] = origin_url
        repo_config['needed'] = needed or repo_config.get('needed', False)
        repo_config['hardlinks'] = list(set(repo_config.get('hardlinks', []) + (hardlinks or [])))
    else:
        # Create new repo entry
        repo_config = {
            'name': repo_name,
            'origin': origin_url,
            'needed': needed,
            'hardlinks': hardlinks or []
        }
        config['repos'].append(repo_config)

    save_config(config)

    for hardlink in repo_config.get('hardlinks', []):
        setup_hardlink(repo_path, hardlink)

    current_status, _ = get_status(repo_path, verbose=True)
    print(f"Linked {repo_name}: {current_status}")

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Manage your Git repositories.")
    subparsers = parser.add_subparsers(dest='command')

    status_parser = subparsers.add_parser('status')
    status_parser.add_argument('repo', nargs='?', help='Name of the repo')

    subparsers.add_parser('orphans')

    get_parser = subparsers.add_parser('get')
    get_parser.add_argument('repo', nargs='?', help='Name of the repo')

    remove_parser = subparsers.add_parser('remove')
    remove_parser.add_argument('repo', help='Name of the repo')
    remove_parser.add_argument('--force', action='store_true', help='Force removal of repo')

    link_parser = subparsers.add_parser('link')
    link_parser.add_argument('repo', help='Name of the repo')
    link_parser.add_argument('-H', '--hardlink', action='append', help='Add hardlink')
    link_parser.add_argument('-n', '--needed', action='store_true', help='Mark repo as needed')

    return parser.parse_args()

def main():
    args = parse_args()

    if args.command == 'status':
        status(args.repo)
    elif args.command == 'orphans':
        find_orphans()
    elif args.command == 'get':
        get(args.repo)
    elif args.command == 'remove':
        remove(args.repo, args.force)
    elif args.command == 'link':
        link(args.repo, args.hardlink, args.needed)

if __name__ == '__main__':
    main()
