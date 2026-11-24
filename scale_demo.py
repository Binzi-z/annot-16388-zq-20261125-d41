#!/usr/bin/env python3
"""Run the required local demonstration: short certificates + 50k paragraphs.

This script uses only the Python 3.12 standard library.  It is safe to rerun;
generated JSON/Markdown lives under ``artifacts/``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from desens_review.corpus import (
    generate_corpus,
    update_one_document,
    verify_corpus,
)
from desens_review.report import write_short_reports

ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"


def main() -> int:
    started = time.perf_counter()
    ARTIFACTS.mkdir(exist_ok=True)

    short_summary = write_short_reports(ARTIFACTS / "short")

    corpus_root = ARTIFACTS / "corpus"
    generation_started = time.perf_counter()
    generate_corpus(corpus_root)
    generation_seconds = time.perf_counter() - generation_started

    update_started = time.perf_counter()
    update_result = update_one_document(corpus_root, "DOC-0007", 0)
    update_seconds = time.perf_counter() - update_started

    verification_started = time.perf_counter()
    verification = verify_corpus(corpus_root)
    verification_seconds = time.perf_counter() - verification_started
    manifest_after_update = json.loads(
        (corpus_root / "manifest.json").read_text(encoding="utf-8")
    )

    output = {
        "ok": verification["ok"]
        and update_result["internal_check"]["stats_match_markers"],
        "python_note": "Run with native Windows Python 3.12: py -3.12 scale_demo.py",
        "short_summary": short_summary,
        "corpus": {
            "root": str(corpus_root),
            "config": manifest_after_update["config"],
            "totals": manifest_after_update["totals"],
            "aggregate_marker_sha256_after_update": manifest_after_update[
                "aggregate_marker_sha256"
            ],
        },
        "update": update_result,
        "verification": verification,
        "timing_seconds": {
            "generation": generation_seconds,
            "update_one_document": update_seconds,
            "full_verification": verification_seconds,
            "total": time.perf_counter() - started,
        },
    }
    (ARTIFACTS / "scale_check.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "ok": output["ok"],
        "scale_check": str(ARTIFACTS / "scale_check.json"),
        "paragraphs": verification["paragraphs_checked"],
        "documents": verification["documents_checked"],
        "errors": verification["errors"],
        "timing_seconds": output["timing_seconds"],
    }, ensure_ascii=False, indent=2))
    return 0 if output["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
