#!/usr/bin/python
# Takes an input PDF and converts it to a folder of PNG images at the given resolution.
# This allows AI to read PDFs with important formatting/designs intact, rather than just
# pulling their text content.
#
# Requirements:
#   - poppler-utils

import argparse
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_dependencies():
    """Ensure pdftoppm and pdfinfo are available on PATH."""
    missing = []
    for tool in ("pdftoppm", "pdfinfo"):
        if shutil.which(tool) is None:
            missing.append(tool)
    if missing:
        print(f"[error] Missing required tools: {', '.join(missing)}", file=sys.stderr)
        print(
            "        Install poppler-utils:\n"
            "          Ubuntu/Debian : sudo apt install poppler-utils\n"
            "          macOS         : brew install poppler\n"
            "          Fedora/RHEL   : sudo dnf install poppler-utils",
            file=sys.stderr,
        )
        sys.exit(1)


def get_page_count(pdf_path: Path) -> int:
    """Return the number of pages in the PDF using pdfinfo."""
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"[error] pdfinfo failed:\n{e.stderr}", file=sys.stderr)
        sys.exit(1)

    for line in result.stdout.splitlines():
        if line.lower().startswith("pages:"):
            return int(line.split(":")[1].strip())

    print("[error] Could not determine page count from pdfinfo output.", file=sys.stderr)
    sys.exit(1)


def convert_page(pdf_path: Path, output_dir: Path, page_num: int, dpi: int) -> tuple[int, bool, str]:
    """
    Convert a single PDF page to PNG.

    pdftoppm writes files as <prefix>-<n>.ppm by default, but with -png and
    a carefully chosen prefix we can control the output path directly.
    We use a temp prefix and rename to the final page_n.png name.

    Returns (page_num, success, message).
    """
    # pdftoppm -png -r <dpi> -f <n> -l <n> <input.pdf> <output_prefix>
    # It will write:  <output_prefix>-<zero_padded_n>.png
    # We use a per-page prefix so parallel writes never collide.
    prefix = str(output_dir / f"_tmp_page_{page_num}")
    final_path = output_dir / f"page_{page_num}.png"

    cmd = [
        "pdftoppm",
        "-png",
        "-r", str(dpi),
        "-f", str(page_num),
        "-l", str(page_num),
        str(pdf_path),
        prefix,
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        return page_num, False, e.stderr.strip()

    # pdftoppm names the file with a zero-padded suffix based on total digits.
    # Since we're always extracting exactly one page, glob for the tmp file.
    tmp_files = list(output_dir.glob(f"_tmp_page_{page_num}-*.png"))
    if not tmp_files:
        return page_num, False, "pdftoppm produced no output file."

    # Rename to the clean final name.
    tmp_files[0].rename(final_path)
    return page_num, True, str(final_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert a PDF into a folder of PNG images (one per page).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("pdf", help="Path to the input PDF file.")
    parser.add_argument("output_dir", help="Directory to write PNG images into (created if absent).")
    parser.add_argument(
        "--dpi", "-d",
        type=int,
        default=150,
        help="Resolution in DPI for the output images.",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Number of parallel workers. Defaults to the number of CPU cores.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output directory if it already exists.",
    )
    args = parser.parse_args()

    # --- Validate inputs ---
    check_dependencies()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.is_file():
        print(f"[error] File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)
    if pdf_path.suffix.lower() != ".pdf":
        print(f"[warning] File does not have a .pdf extension: {pdf_path}", file=sys.stderr)

    if args.dpi < 1 or args.dpi > 1200:
        print(f"[error] DPI must be between 1 and 1200. Got: {args.dpi}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir).resolve()
    if output_dir.exists():
        if not args.overwrite:
            print(
                f"[error] Output directory already exists: {output_dir}\n"
                "        Use --overwrite to replace it.",
                file=sys.stderr,
            )
            sys.exit(1)
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    # --- Get page count ---
    page_count = get_page_count(pdf_path)
    print(f"[info]  PDF     : {pdf_path}")
    print(f"[info]  Pages   : {page_count}")
    print(f"[info]  DPI     : {args.dpi}")
    print(f"[info]  Output  : {output_dir}")

    workers = args.workers or os.cpu_count() or 4
    workers = min(workers, page_count)  # No point spawning more workers than pages.
    print(f"[info]  Workers : {workers}")
    print()

    # --- Parallel conversion ---
    failed = []
    completed = 0

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(convert_page, pdf_path, output_dir, n, args.dpi): n
            for n in range(1, page_count + 1)
        }

        for future in as_completed(futures):
            page_num, success, message = future.result()
            if success:
                completed += 1
                # Overwrite the line for a live progress counter.
                print(f"\r[progress] {completed}/{page_count} pages converted", end="", flush=True)
            else:
                failed.append((page_num, message))
                print(f"\n[error]  Page {page_num} failed: {message}", file=sys.stderr)

    print()  # Newline after progress line.

    # --- Summary ---
    if failed:
        print(f"\n[done]  Completed with errors. {completed}/{page_count} pages converted.")
        print("        Failed pages:", ", ".join(str(p) for p, _ in sorted(failed)))
        sys.exit(2)
    else:
        print(f"[done]  All {page_count} pages converted successfully → {output_dir}")


if __name__ == "__main__":
    main()
