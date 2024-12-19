#!/usr/bin/env python3
# A unified package manager frontend built on custom Bash recipes.
#
# Requirements:
#   - $ACE_PACKAGES_DIR: the directory where package configs can be found

import json
import sys
import os
import subprocess
from pathlib import Path
import argparse

PACKAGES_DIR = Path(os.environ["ACE_PACKAGES_DIR"])

def execute_recipe(pkg_name, recipe_path, operation):
    """
    Executes the recipe at the given path with the given operation and package name (provided as
    arguments). This is designed to execute bash package installation/removal recipes.
    """

    exit_code = subprocess.call(
        [ "bash", PACKAGES_DIR / recipe_path, operation, pkg_name ],
        shell = False,
        # Forward all stdio streams
        stdin = None,
        stdout = None,
        stderr = None
    )
    if exit_code != 0:
        print(f"Error: failed to execute recipe for package '{pkg_name}', using recipe at '{recipe_path}'. The operation has *not* been recorded in the registry.")
        sys.exit(1)

def install_package(raw_name):
    """
    Installs the package with the given name.
    """

    # Skip if package is already installed
    registry_entry = get_registry_entry(raw_name)
    if registry_entry is not None:
        print(f"Package '{raw_name}' is already installed.")
        sys.exit(1)

    desc = input(f"Enter a description for package '{raw_name}': ")

    recipe_path, name = get_recipe_path(raw_name)
    print(f"Installing package '{name}' using recipe at '{recipe_path}'...")
    if confirm("Proceed with installation?"):
        execute_recipe(name, recipe_path, "install")

        # Record the package as having been installed
        add_to_registry(name, desc, recipe_path)
        print(f"Package '{name}' has been successfully installed.")
    else:
        print("Aborted.")
        sys.exit(1)

def remove_package(raw_name):
    """
    Removes the package with the given name.
    """

    recipe_path, name = get_recipe_path(raw_name)
    print(f"Removing package '{name}' using recipe at '{recipe_path}'...")
    if confirm("Proceed with removal?"):
        execute_recipe(name, recipe_path, "remove")

        # Remove the package from the registry
        remove_from_registry(name)
        print(f"Package '{name}' has been successfully removed.")
    else:
        print("Aborted.")
        sys.exit(1)

def reinstall_package(raw_name):
    """
    Reinstalls the package with the given name.
    """

    recipe_path, name = get_recipe_path(raw_name)
    print(f"Reinstalling package '{name}' using recipe at '{recipe_path}'...")
    if confirm("Proceed with reinstallation?"):
        execute_recipe(name, recipe_path, "remove")
        execute_recipe(name, recipe_path, "install")
        print(f"Package '{name}' has been successfully reinstalled.")
    else:
        print("Aborted.")
        sys.exit(1)

def list_packages():
    """
    Lists all packages in the registry.
    """

    registry = get_registry()
    for pkg_info in registry:
        print(f"{pkg_info['name']}: {pkg_info['description']}")

def rebuild_packages():
    """
    Installs every package in the registry without prompting. This is designed to be used after
    migrating to a new system, where none of the previously installed packages are available yet.
    """

    registry = get_registry()
    for pkg_info in registry:
        name = pkg_info["name"]
        recipe_path = pkg_info["recipe_path"]
        print(f"Rebuilding package '{name}' using recipe at '{recipe_path}'...")
        execute_recipe(name, recipe_path, "install")

def get_recipe_path(raw_name):
    """
    Determines the recipe path to use from the given input string, which will be either a raw
    package name, or something of the form `source::package`. Returns the path to the recipe,
    which is checked to exist, and the name of the package.

    If the package is known in the registry, the recipe path is taken from the registry entry,
    and confirmation is requested if the computed recipe path would be different.
    """

    # Decompose the raw name and compute the path naively
    parts = raw_name.split("::")
    if len(parts) == 1:
        name = parts[0]
        source = None
        recipe_path = f"recipes/{raw_name}.sh"
    elif len(parts) == 2:
        name = parts[0]
        source = parts[1]
        recipe_path = f"sources/{source}.sh"
    else:
        print(f"Error: invalid package name '{raw_name}' (expected either `package` or `source::package`).")
        sys.exit(1)

    # Now check if we already know the recipe path; if we do, make sure they're the same
    registry_entry = get_registry_entry(name)
    if registry_entry is not None:
        registry_recipe_path = registry_entry["recipe_path"]
        if registry_recipe_path != recipe_path:
            print(f"Warning: package '{name}' has a different recipe path in the registry ('{registry_recipe_path}') than the computed path ('{recipe_path}')! Aborting...")
            sys.exit(1)

    if not (PACKAGES_DIR / recipe_path).exists():
        print(f"Error: no recipe found for package '{raw_name}' (tried '{recipe_path}').")
        sys.exit(1)
    else:
        return recipe_path, parts[-1]

def get_registry():
    """
    Retrieves the registry as a list of dictionaries, where each dictionary represents a package.
    """

    registry = []
    with open(PACKAGES_DIR / "registry.jsonl", 'r') as registry_file:
        for line in registry_file:
            try:
                pkg_info = json.loads(line)
                registry.append(pkg_info)
            except json.JSONDecodeError:
                print(f"Error parsing JSON in registry file at line {line.strip()}. Please correct this error manually.")
                sys.exit(1)

    return registry

def add_to_registry(name, desc, recipe_path):
    """
    Adds the package with the given name and recipe path to the registry.
    """

    with open(PACKAGES_DIR / "registry.jsonl", 'a') as registry_file:
        registry_file.write(json.dumps({ "name": name, "description": desc, "recipe_path": recipe_path }) + "\n")

def remove_from_registry(name):
    """
    Removes the package with the given name from the registry.
    """

    registry = get_registry()
    with open(PACKAGES_DIR / "registry.jsonl", 'w') as registry_file:
        for pkg_info in registry:
            if pkg_info["name"] != name:
                registry_file.write(json.dumps(pkg_info) + "\n")

def get_registry_entry(name):
    """
    Retrieves the registry entry for the package with the given name, returning it as a dictionary.
    """

    registry = get_registry()
    for pkg_info in registry:
        if pkg_info["name"] == name:
            return pkg_info
    return None

def confirm(msg):
    """
    Prompts the user to confirm the given message, returning True if they do, False otherwise.
    """

    while True:
        confirm = input(f"{msg} [y/n]: ")
        if confirm.lower() == "y":
            return True
        elif confirm.lower() == "n":
            return False
        else:
            print("Invalid input. Please enter 'y' or 'n'.")

def main():
    parser = argparse.ArgumentParser(description="A unified package manager frontend built on custom Bash recipes.")
    subparsers = parser.add_subparsers(dest="command", help="The command to execute")
    
    install_parser = subparsers.add_parser("install", help="Install packages")
    install_parser.add_argument("packages", nargs="+", help="The package(s) to install")

    remove_parser = subparsers.add_parser("remove", help="Remove packages")
    remove_parser.add_argument("packages", nargs="+", help="The package(s) to remove")

    reinstall_parser = subparsers.add_parser("reinstall", help="Reinstall packages")
    reinstall_parser.add_argument("packages", nargs="+", help="The package(s) to reinstall")

    list_parser = subparsers.add_parser("list", help="List installed packages")

    rebuild_parser = subparsers.add_parser("rebuild", help="Install all packages on a new system")

    args = parser.parse_args()
    
    if args.command == "install":
        for pkg in args.packages:
            install_package(pkg)
    elif args.command == "remove":
        for pkg in args.packages:
            remove_package(pkg)
    elif args.command == "reinstall":
        for pkg in args.packages:
            reinstall_package(pkg)
    elif args.command == "list":
        list_packages()
    elif args.command == "rebuild":
        rebuild_packages()

if __name__ == "__main__":
    main()
