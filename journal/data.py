#!/usr/bin/env python
# Extracts data from journal tracking files and saves it to a CSV file for in-depth processing.
# If passed a path to a CSV file, this will only collect data more recent than the last point in
# that file.
#
# Requirements:
#   - $ACE_JOURNALS_DIR

import os, sys, json, csv, argparse
from datetime import datetime

def discover_jsons(base_dir):
    """
    Walk base_dir and yield tuples (date_str, filepath)
    where date_str is 'YYYY-MM-DD' based on the path
    layout base_dir/YYYY/MM/DD.json.
    """
    for root, _dirs, files in os.walk(base_dir):
        for fn in files:
            if not fn.lower().endswith('.json'):
                continue
            full = os.path.join(root, fn)
            # derive relative path pieces
            rel = os.path.relpath(full, base_dir)
            parts = rel.split(os.sep)
            # expect parts == [YYYY, MM, DD.json]
            if len(parts) < 3:
                continue
            year, month = parts[0], parts[1]
            day = os.path.splitext(parts[2])[0]
            # sanity check numeric
            try:
                y = int(year); m = int(month); d = int(day)
            except ValueError:
                continue
            date_str = f"{y:04d}-{m:02d}-{d:02d}"
            yield date_str, full

def load_all_data(base_dir):
    """
    Returns a dict date_str -> data_dict,
    and a set of all keys seen.
    """
    data = {}
    all_keys = set()
    for date_str, path in discover_jsons(base_dir):
        try:
            with open(path, 'r', encoding='utf8') as f:
                obj = json.load(f)
        except Exception as e:
            print(f"Warning: failed to parse {path}: {e}", file=sys.stderr)
            continue
        if not isinstance(obj, dict):
            continue
        data[date_str] = obj
        all_keys.update(obj.keys())
    return data, all_keys

def read_existing_csv(path):
    """
    Reads the existing CSV, returns (header, last_date_str).
    header is a list of column names.
    last_date_str is the date in the first column of the last non-empty row,
    or None if no data rows.
    """
    last = None
    with open(path, newline='', encoding='utf8') as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise RuntimeError(f"{path} is empty")
        for row in reader:
            if row and row[0].strip():
                last = row[0].strip()
    return header, last

def write_new_csv(outpath, data_map, all_keys):
    """
    Write a brand-new CSV to outpath, with columns: date + sorted(all_keys).
    data_map: date_str -> dict
    """
    dates = sorted(data_map.keys())
    keys = sorted(all_keys)
    header = ["date"] + keys
    with open(outpath, 'w', newline='', encoding='utf8') as f:
        w = csv.writer(f)
        w.writerow(header)
        for dt in dates:
            row = [dt] + [ data_map[dt].get(k, "") for k in keys ]
            w.writerow(row)
    print(f"Wrote {len(dates)} rows to {outpath}")

def append_to_existing(path, data_map, existing_header, last_date):
    """
    Append rows for dates > last_date to the CSV at path.
    existing_header is a list of column names (first should be 'date' or similar).
    We'll only include those columns; extra keys in data_map are ignored.
    """
    # filter new dates
    dates = sorted(d for d in data_map if last_date is None or d > last_date)
    if not dates:
        print("No new data to append.")
        return
    # detect any new keys that aren't in existing_header
    all_keys_in_data = set().union(*(data_map[d].keys() for d in dates))
    extra = all_keys_in_data - set(existing_header)
    if extra:
        print("Warning: the following new keys will be ignored (not in existing CSV columns):",
              ", ".join(sorted(extra)), file=sys.stderr)
    # we will map each column name to its index; but really just iterate header
    with open(path, 'a', newline='', encoding='utf8') as f:
        w = csv.writer(f)
        for dt in dates:
            rec = data_map[dt]
            row = []
            for col in existing_header:
                if col == existing_header[0]:
                    # first column: date
                    row.append(dt)
                else:
                    row.append(rec.get(col, ""))
            w.writerow(row)
    print(f"Appended {len(dates)} rows to {path}")

def main():
    p = argparse.ArgumentParser(
        description="Collect JSON journal files into a single CSV.")
    me = p.add_mutually_exclusive_group(required=True)
    me.add_argument("-o", "--output",
                    help="write a brand-new CSV here")
    me.add_argument("-e", "--existing",
                    help="append to this CSV (only dates after its last line)")
    args = p.parse_args()

    base = os.getenv("ACE_JOURNALS_DIR")
    if not base:
        p.error("Please set ACE_JOURNALS_DIR in your environment.")
    if not os.path.isdir(base):
        p.error(f"ACE_JOURNALS_DIR={base} is not a directory")

    data_map, all_keys = load_all_data(base)
    if not data_map:
        print("No JSON data found under", base, file=sys.stderr)
        sys.exit(1)

    if args.output:
        write_new_csv(args.output, data_map, all_keys)
    else:
        # append mode
        hdr, last_date = read_existing_csv(args.existing)
        # sanity: first column must be date-ish
        if len(hdr) < 1:
            sys.exit("Existing CSV has no columns")
        append_to_existing(args.existing, data_map, hdr, last_date)

if __name__ == "__main__":
    main()
