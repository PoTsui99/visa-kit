#!/usr/bin/env python3
"""Copy the official appointment letter and checklist without modifying either PDF."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
try:
    from pypdf import PdfReader
except ImportError:
    raise SystemExit("Missing pypdf. Use the configured PDF runtime or install pypdf from a trusted package source.")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_print_pack(appointment, checklist, destination):
    pairs = [
        (Path(appointment).expanduser().resolve(), "01_Appointment_Confirmation.pdf"),
        (Path(checklist).expanduser().resolve(), "02_UKVI_Document_Checklist.pdf"),
    ]
    dest = Path(destination).expanduser().resolve()
    if pairs[0][0] == pairs[1][0]:
        raise ValueError("Appointment letter and document checklist must be distinct source files.")
    expected_names = {name for _, name in pairs}
    if dest.exists() and not dest.is_dir():
        raise ValueError("Destination is not a directory: " + str(dest))
    if dest.exists():
        extras = [p.name for p in dest.iterdir() if p.suffix.lower() == ".pdf" and p.name not in expected_names]
        if extras:
            raise FileExistsError("Destination contains other PDFs; choose a clean print folder: " + ", ".join(sorted(extras)))
    page_counts = {}
    for source, name in pairs:
        if not source.is_file() or source.suffix.lower() != ".pdf":
            raise ValueError("Missing PDF source: " + str(source))
        try:
            reader = PdfReader(source)
            if reader.is_encrypted or not reader.pages:
                raise ValueError("Print source is encrypted or has no pages: " + str(source))
            page_counts[name] = len(reader.pages)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Invalid PDF print source: " + str(source)) from exc
        target = dest / name
        if target.exists() and (not target.is_file() or digest(source) != digest(target)):
            raise FileExistsError("Different print file already exists; review it instead of overwriting: " + str(target))
    dest.mkdir(parents=True, exist_ok=True)
    records = []
    for source, name in pairs:
        target = dest / name
        if not target.exists():
            shutil.copy2(source, target)
        expected = digest(source)
        if digest(target) != expected:
            raise OSError("Print copy failed byte-integrity verification: " + str(target))
        records.append({"source": str(source), "print_copy": str(target), "sha256": expected, "pages": page_counts[name]})
    return {
        "status": "copied_and_verified",
        "destination": str(dest),
        "documents": records,
        "note": "Check actual page counts before printing. Leave any appointment-only signature fields blank.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--appointment", required=True, type=Path)
    parser.add_argument("--checklist", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build_print_pack(args.appointment, args.checklist, args.destination)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
