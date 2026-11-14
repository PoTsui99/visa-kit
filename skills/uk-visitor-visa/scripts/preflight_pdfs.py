#!/usr/bin/env python3
"""Check explicitly selected PDF upload copies without changing their bytes."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

try:
    from pypdf import PdfReader
except ImportError:
    raise SystemExit("Missing pypdf. Use the configured PDF runtime or install pypdf from a trusted package source.")

ENGLISH_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. -]*\.pdf", re.ASCII | re.IGNORECASE)


def inspect_files(files, max_bytes=5_000_000):
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    paths = [Path(item).expanduser().resolve() for item in files]
    names = Counter(p.name.casefold() for p in paths)
    records = []
    for path in paths:
        record = {
            "path": str(path), "filename": path.name, "bytes": None,
            "pages": None, "encrypted": None, "sha256": None,
            "errors": [], "warnings": [],
        }
        if names[path.name.casefold()] > 1:
            record["errors"].append("duplicate_filename")
        if not ENGLISH_FILENAME.fullmatch(path.name):
            record["errors"].append("filename_requires_english_safe_characters")
        if not path.is_file():
            record["errors"].append("missing_or_not_a_file")
            records.append(record)
            continue
        try:
            data = path.read_bytes()
            record["bytes"] = len(data)
            record["sha256"] = hashlib.sha256(data).hexdigest()
            if not data:
                record["errors"].append("empty_file")
            if len(data) >= max_bytes:
                record["errors"].append("not_below_size_limit")
            reader = PdfReader(path)
            record["encrypted"] = reader.is_encrypted
            if reader.is_encrypted:
                record["errors"].append("encrypted_pdf_requires_a_separate_upload_copy")
            else:
                record["pages"] = len(reader.pages)
                if not reader.pages:
                    record["errors"].append("no_pages")
                fields = reader.get_fields() or {}
                if any(str(field.get("/FT", "")) == "/Sig" for field in fields.values()):
                    record["warnings"].append("signature_field_present_preserve_original_bytes")
        except Exception as exc:
            record["errors"].append("unreadable_or_invalid_pdf")
            record["warnings"].append("reader_error_type:" + type(exc).__name__)
        records.append(record)
    return {
        "status": "blocked" if any(r["errors"] for r in records) else "passed",
        "max_bytes_exclusive": max_bytes,
        "file_count": len(records),
        "scope": "Structural preflight only; not translation, visual, authenticity or submission verification.",
        "documents": records,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", nargs="+", required=True, help="Explicit PDFs approved for this application; no folder auto-scan")
    parser.add_argument("--max-bytes", type=int, default=5_000_000)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    if args.max_bytes <= 0:
        parser.error("--max-bytes must be positive")
    report = inspect_files(args.files, args.max_bytes)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_output:
        output = args.json_output.expanduser().resolve()
        if output in {Path(x).expanduser().resolve() for x in args.files}:
            parser.error("--json-output must not overwrite an input PDF")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 1 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
