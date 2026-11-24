from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path
from typing import Sequence

from .align import enumerate_optimal_alignments
from .transport import TransportLattice, enumerate_transport_alignments
from .corpus import (
    DEFAULT_DOCUMENTS,
    DEFAULT_PARAGRAPHS_PER_DOC,
    DEFAULT_SEED,
    generate_corpus,
    update_one_document,
    verify_corpus,
)
from .model import character_atoms, word_atoms
from .report import write_short_reports


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_enumerate(args: argparse.Namespace) -> int:
    atoms = character_atoms if args.mode == "char" else word_atoms
    source = atoms(args.source)
    target = atoms(args.target)
    if args.alignment_model == "transport":
        lattice = TransportLattice(source, target)
        alignments = enumerate_transport_alignments(source, target)
    else:
        from .align import Lattice

        lattice = Lattice(source, target)
        alignments = enumerate_optimal_alignments(source, target)

    records = []
    for alignment in alignments:
        records.append(
            {
                **alignment.to_dict(),
                "links": alignment.links,
                "diagram": lattice.diagram(alignment),
                "verification": lattice.verify_alignment(alignment),
            }
        )
    result = {
        "source": args.source,
        "target": args.target,
        "mode": args.mode,
        "alignment_model": args.alignment_model,
        "minimum_cost": lattice.total_cost,
        "lattice_alignment_count": lattice.total_paths,
        "alignment_count": len(alignments),
        "alignments": records,
    }
    _print_json(result)
    return 0


def cmd_scenarios(args: argparse.Namespace) -> int:
    summary = write_short_reports(args.out)
    _print_json({"out": str(Path(args.out).resolve()), **summary})
    return 0


def cmd_generate_corpus(args: argparse.Namespace) -> int:
    manifest = generate_corpus(
        args.root,
        documents=args.documents,
        paragraphs_per_doc=args.paragraphs_per_doc,
        seed=args.seed,
    )
    _print_json(
        {
            "root": str(Path(args.root).resolve()),
            "config": manifest["config"],
            "totals": manifest["totals"],
            "aggregate_marker_sha256": manifest["aggregate_marker_sha256"],
        }
    )
    return 0


def cmd_update_one(args: argparse.Namespace) -> int:
    result = update_one_document(
        args.root,
        doc_id=args.doc,
        paragraph_index=args.paragraph,
        inserted_token=args.token,
    )
    _print_json(result)
    return 0


def cmd_verify_corpus(args: argparse.Namespace) -> int:
    result = verify_corpus(args.root)
    _print_json(result)
    return 0 if result["ok"] else 2


def cmd_test(_args: argparse.Namespace) -> int:
    loader = unittest.TestLoader()
    start = Path(__file__).resolve().parent.parent / "tests"
    suite = loader.discover(str(start), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m desens_review",
        description="Offline cross-version desensitization alignment reviewer",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_enum = sub.add_parser("enumerate", help="enumerate all minimum alignments of short strings")
    p_enum.add_argument("--source", required=True)
    p_enum.add_argument("--target", required=True)
    p_enum.add_argument("--mode", choices=["char", "word"], default="char")
    p_enum.add_argument(
        "--alignment-model",
        choices=["transport", "ordered"],
        default="transport",
        help="transport allows crossing moved links; ordered is classic Levenshtein",
    )
    p_enum.set_defaults(func=cmd_enumerate)

    p_scenarios = sub.add_parser("scenarios", help="write audited short-string scenario reports")
    p_scenarios.add_argument("--out", default="artifacts/short")
    p_scenarios.set_defaults(func=cmd_scenarios)

    p_gen = sub.add_parser("generate-corpus", help="generate >=50k synthetic paragraphs")
    p_gen.add_argument("--root", default="artifacts/corpus")
    p_gen.add_argument("--documents", type=int, default=DEFAULT_DOCUMENTS)
    p_gen.add_argument("--paragraphs-per-doc", type=int, default=DEFAULT_PARAGRAPHS_PER_DOC)
    p_gen.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p_gen.set_defaults(func=cmd_generate_corpus)

    p_upd = sub.add_parser("update-one", help="incrementally update and realign one document")
    p_upd.add_argument("--root", default="artifacts/corpus")
    p_upd.add_argument("--doc", default="DOC-0007")
    p_upd.add_argument("--paragraph", type=int, default=0)
    p_upd.add_argument("--token", default="late_revision_token")
    p_upd.set_defaults(func=cmd_update_one)

    p_ver = sub.add_parser("verify-corpus", help="full recomputation and marker consistency check")
    p_ver.add_argument("--root", default="artifacts/corpus")
    p_ver.set_defaults(func=cmd_verify_corpus)

    p_test = sub.add_parser("test", help="run the standard-library unittest suite")
    p_test.set_defaults(func=cmd_test)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
