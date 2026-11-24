from __future__ import annotations

import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from .model import ClassifiedSpan, Downgrade, Level, ReviewCase
from .review import compact_markers

DEFAULT_DOCUMENTS = 500
DEFAULT_PARAGRAPHS_PER_DOC = 100
DEFAULT_SEED = 20261125

_VOCAB = [
    "river", "ledger", "window", "garden", "signal", "market", "bridge",
    "copper", "winter", "orbit", "letter", "engine", "forest", "silver",
    "morning", "harbor", "pencil", "meadow", "stone", "thread", "beacon",
    "cipher", "lantern", "anchor", "basket", "circle", "dragon", "ember",
    "falcon", "granite", "island", "jungle", "kettle", "lemon", "marble",
]


def canonical_dumps(obj: Any) -> bytes:
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_json(obj: Any) -> str:
    return hashlib.sha256(canonical_dumps(obj)).hexdigest()


def _char_span(words: list[str], first: int, past_last: int) -> tuple[int, int]:
    left = sum(len(w) + 1 for w in words[:first])
    count = past_last - first
    right = left + sum(len(w) for w in words[first:past_last]) + max(0, count - 1)
    return left, right


def make_paragraph_case(index: int, seed: int = DEFAULT_SEED) -> ReviewCase:
    """Generate one independent synthetic paragraph/review case."""

    rng = random.Random(seed + index * 1_000_003)
    n = rng.randint(8, 14)
    words = [rng.choice(_VOCAB) for _ in range(n)]

    phrase_pos = rng.randint(1, len(words) - 2)
    source_id = f"S-P{index:06d}"
    level = int(Level.SECRET) if index % 7 else int(Level.CONFIDENTIAL)
    words[phrase_pos : phrase_pos + 0] = []  # explicit no-op for readability
    words.insert(phrase_pos + 1, "lantern")
    words.insert(phrase_pos + 1, "cipher")
    # Phrase now occupies phrase_pos + 1 and phrase_pos + 2? Correct below.
    first = phrase_pos + 1
    past_last = first + 2
    left, right = _char_span(words, first, past_last)

    source_text = " ".join(words)
    target_words = words.copy()
    operation = index % 8

    if operation == 0 and len(target_words) > 8:
        del target_words[rng.randrange(0, len(target_words))]
    elif operation == 1:
        target_words.insert(rng.randrange(len(target_words) + 1), rng.choice(_VOCAB))
    elif operation == 2:
        # Move the classified two-token phrase.
        phrase = target_words[first:past_last]
        del target_words[first:past_last]
        dest = rng.randrange(len(target_words) + 1)
        target_words[dest:dest] = phrase
    elif operation == 3:
        # Copy one classified token elsewhere.
        dest = rng.randrange(len(target_words) + 1)
        target_words.insert(dest, words[first])
    elif operation == 4:
        # Split the phrase by inserting a filler between its tokens.
        target_words.insert(first + 1, rng.choice(_VOCAB))
    elif operation == 5 and len(target_words) >= 4:
        # Duplicate a repeated ordinary interval.
        start = rng.randrange(0, len(target_words) - 1)
        pair = target_words[start : start + 2]
        dest = min(len(target_words), start + 3)
        target_words[dest:dest] = pair
    elif operation == 6 and len(target_words) > 8:
        # Move a single ordinary word.
        src_pos = rng.randrange(len(target_words))
        word = target_words.pop(src_pos)
        dest = rng.randrange(len(target_words) + 1)
        target_words.insert(dest, word)
    else:
        target_words.insert(rng.randrange(len(target_words) + 1), rng.choice(_VOCAB))

    downgrades: list[Downgrade] = []
    if index % 101 == 0:
        downgrades.append(
            Downgrade(
                f"DG-OK-{index:06d}",
                source_id,
                watermark=int(Level.PUBLIC),
                proxy=False,
                note="synthetic active scoped declassification",
            )
        )
    if index % 103 == 0:
        downgrades.append(
            Downgrade(
                f"DG-REVOKED-PROXY-{index:06d}",
                source_id,
                watermark=int(Level.PUBLIC),
                active=False,
                proxy=True,
                revocation_id=f"REV-{index:06d}",
                note="synthetic revoked proxy downgrade",
            )
        )

    return ReviewCase(
        case_id=f"P{index:06d}",
        source_text=source_text,
        target_text=" ".join(target_words),
        spans=[ClassifiedSpan(source_id, left, right, level, "synthetic classified phrase")],
        downgrades=downgrades,
        editor=f"editor-{index % 17:02d}",
        parent_version=f"synthetic-v{index % 5}",
        atom_mode="word",
    )


def make_paragraph_dict(index: int, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    return make_paragraph_case(index, seed).to_dict()


def summarize_markers(markers: list[dict[str, Any]]) -> dict[str, int]:
    totals = Counter()
    totals["paragraphs"] = len(markers)
    for marker in markers:
        for key in (
            "source_atoms",
            "target_atoms",
            "dp_cells",
            "optimal_cost",
            "choice_count",
            "may_sensitive_atoms",
            "must_sensitive_atoms",
        ):
            if key == "choice_count":
                totals[key] += int(marker.get(key, 0))
            elif key in marker:
                totals[key] += int(marker[key])
        totals["optimal_path_count_sum"] += int(marker.get("optimal_path_count", 0))
        totals["may_targets"] += len(marker.get("may_targets", []))
        totals["must_targets"] += len(marker.get("must_targets", []))
        totals["may_intervals"] += len(marker.get("may_intervals", []))
        totals["must_intervals"] += len(marker.get("must_intervals", []))
        totals["conflict_targets"] += len(marker.get("conflict_targets", []))
        if marker.get("decision") == "BLOCK":
            totals["blocked_paragraphs"] += 1
    return dict(sorted(totals.items()))


def process_document_payload(payload: dict[str, Any]) -> dict[str, Any]:
    markers: list[dict[str, Any]] = []
    for case_dict in payload["cases"]:
        case = ReviewCase.from_dict(case_dict)
        markers.append(compact_markers(case))
    return {
        "doc_id": payload["doc_id"],
        "stats": summarize_markers(markers),
        "markers": markers,
    }


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def generate_corpus(
    root: str | Path,
    documents: int = DEFAULT_DOCUMENTS,
    paragraphs_per_doc: int = DEFAULT_PARAGRAPHS_PER_DOC,
    seed: int = DEFAULT_SEED,
    minimum_paragraphs: int = 50_000,
) -> dict[str, Any]:
    if documents < 1 or paragraphs_per_doc < 1:
        raise ValueError("documents and paragraphs_per_doc must be positive")
    total = documents * paragraphs_per_doc
    if total < minimum_paragraphs:
        raise ValueError(
            f"synthetic corpus has {total} paragraphs; need >={minimum_paragraphs}"
        )

    root = Path(root)
    cases_dir = root / "cases"
    markers_dir = root / "markers"
    cases_dir.mkdir(parents=True, exist_ok=True)
    markers_dir.mkdir(parents=True, exist_ok=True)

    doc_entries: dict[str, dict[str, Any]] = {}
    totals = Counter()
    for doc_index in range(documents):
        doc_id = f"DOC-{doc_index:04d}"
        first = doc_index * paragraphs_per_doc
        cases = [
            make_paragraph_dict(first + p, seed)
            for p in range(paragraphs_per_doc)
        ]
        payload = {"doc_id": doc_id, "seed": seed, "cases": cases}
        marker_payload = process_document_payload(payload)

        case_path = cases_dir / f"{doc_id}.json"
        marker_path = markers_dir / f"{doc_id}.markers.json"
        case_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        marker_path.write_text(
            json.dumps(marker_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        doc_entries[doc_id] = {
            "case_file": _relative(case_path, root),
            "marker_file": _relative(marker_path, root),
            "case_sha256": sha256_json(payload),
            "marker_sha256": sha256_json(marker_payload),
            "stats": marker_payload["stats"],
        }
        for key, value in marker_payload["stats"].items():
            totals[key] += value

    manifest = {
        "schema": "desens-review-corpus-v1",
        "config": {
            "documents": documents,
            "paragraphs_per_doc": paragraphs_per_doc,
            "total_paragraphs": total,
            "seed": seed,
        },
        "totals": dict(sorted(totals.items())),
        "docs": doc_entries,
    }
    manifest["aggregate_marker_sha256"] = _aggregate_marker_hash(doc_entries)
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def _aggregate_marker_hash(doc_entries: dict[str, dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for doc_id in sorted(doc_entries):
        digest.update(doc_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(doc_entries[doc_id]["marker_sha256"].encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def load_manifest(root: str | Path) -> dict[str, Any]:
    root = Path(root)
    return json.loads((root / "manifest.json").read_text(encoding="utf-8"))


def update_one_document(
    root: str | Path,
    doc_id: str = "DOC-0007",
    paragraph_index: int = 0,
    inserted_token: str = "late_revision_token",
) -> dict[str, Any]:
    root = Path(root)
    manifest = load_manifest(root)
    if doc_id not in manifest["docs"]:
        raise KeyError(f"unknown document {doc_id}")

    entry = manifest["docs"][doc_id]
    case_path = root / entry["case_file"]
    payload = json.loads(case_path.read_text(encoding="utf-8"))
    if not 0 <= paragraph_index < len(payload["cases"]):
        raise IndexError("paragraph_index outside document")

    before_case_hash = sha256_json(payload)
    case = payload["cases"][paragraph_index]
    case["target_text"] = case["target_text"] + " " + inserted_token
    case["editor"] = "incremental-local-update"
    payload["revision"] = int(payload.get("revision", 0)) + 1
    payload["updated_paragraph"] = paragraph_index
    after_case_hash = sha256_json(payload)

    marker_payload = process_document_payload(payload)
    marker_path = root / entry["marker_file"]
    marker_path.write_text(
        json.dumps(marker_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    case_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    entry["case_sha256"] = after_case_hash
    entry["marker_sha256"] = sha256_json(marker_payload)
    entry["stats"] = marker_payload["stats"]
    entry["last_local_update"] = {
        "paragraph_index": paragraph_index,
        "inserted_token": inserted_token,
        "before_case_sha256": before_case_hash,
        "after_case_sha256": after_case_hash,
        "local_alignment_paragraphs": marker_payload["stats"]["paragraphs"],
        "local_dp_cells": marker_payload["stats"]["dp_cells"],
        "local_marker_edges": marker_payload["stats"]["choice_count"],
    }

    totals = Counter()
    for doc_entry in manifest["docs"].values():
        for key, value in doc_entry["stats"].items():
            totals[key] += int(value)
    manifest["totals"] = dict(sorted(totals.items()))
    manifest["aggregate_marker_sha256"] = _aggregate_marker_hash(manifest["docs"])
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    internal_check = {
        "stats_match_markers": marker_payload["stats"]
        == summarize_markers(marker_payload["markers"]),
        "paragraph_count": len(marker_payload["markers"]),
        "dp_cell_sum": sum(m["dp_cells"] for m in marker_payload["markers"]),
        "choice_count_sum": sum(m["choice_count"] for m in marker_payload["markers"]),
    }
    internal_check["dp_cells_stat_consistent"] = (
        internal_check["dp_cell_sum"] == marker_payload["stats"]["dp_cells"]
    )
    return {
        "doc_id": doc_id,
        "paragraph_index": paragraph_index,
        "local_stats": marker_payload["stats"],
        "internal_check": internal_check,
        "manifest_aggregate_marker_sha256": manifest["aggregate_marker_sha256"],
    }


def verify_corpus(root: str | Path, minimum_paragraphs: int = 50_000) -> dict[str, Any]:
    """Recompute every alignment and compare with stored full markers."""

    root = Path(root)
    manifest = load_manifest(root)
    errors: list[str] = []
    checked_docs = 0
    checked_paragraphs = 0
    totals = Counter()

    for doc_id, entry in sorted(manifest["docs"].items()):
        case_path = root / entry["case_file"]
        marker_path = root / entry["marker_file"]
        payload = json.loads(case_path.read_text(encoding="utf-8"))
        stored_markers = json.loads(marker_path.read_text(encoding="utf-8"))

        if sha256_json(payload) != entry["case_sha256"]:
            errors.append(f"{doc_id}: case hash mismatch")
        if sha256_json(stored_markers) != entry["marker_sha256"]:
            errors.append(f"{doc_id}: marker hash mismatch")

        recomputed = process_document_payload(payload)
        if stored_markers != recomputed:
            errors.append(f"{doc_id}: stored alignment markers differ from full recomputation")

        recomputed_stats = summarize_markers(recomputed["markers"])
        if recomputed_stats != recomputed["stats"]:
            errors.append(f"{doc_id}: local stats do not match marker rollup")
        if entry["stats"] != recomputed_stats:
            errors.append(f"{doc_id}: manifest stats do not match recomputation")

        checked_docs += 1
        checked_paragraphs += len(recomputed["markers"])
        for key, value in recomputed_stats.items():
            totals[key] += value

    if checked_paragraphs < minimum_paragraphs:
        errors.append(
            f"only {checked_paragraphs} paragraphs checked; need >={minimum_paragraphs}"
        )
    if dict(sorted(totals.items())) != manifest["totals"]:
        errors.append("manifest totals do not equal full marker rollup")
    expected_aggregate = _aggregate_marker_hash(manifest["docs"])
    if expected_aggregate != manifest.get("aggregate_marker_sha256"):
        errors.append("aggregate marker hash mismatch")

    return {
        "ok": not errors,
        "errors": errors,
        "documents_checked": checked_docs,
        "paragraphs_checked": checked_paragraphs,
        "totals": dict(sorted(totals.items())),
        "aggregate_marker_sha256": manifest.get("aggregate_marker_sha256"),
    }
