from __future__ import annotations

from .model import ClassifiedSpan, Downgrade, Level, ReviewCase


def short_scenarios() -> dict[str, ReviewCase]:
    """Tiny cases whose complete optimal alignment sets are easy to audit."""

    return {
        "copied_fragment": ReviewCase(
            case_id="copied_fragment",
            atom_mode="char",
            source_text="a",
            target_text="aa",
            spans=[ClassifiedSpan("S-COPY", 0, 1, Level.SECRET, "copied atom")],
            editor="editor-copy",
            parent_version="v1",
        ),
        "repeated_source_conflict": ReviewCase(
            case_id="repeated_source_conflict",
            atom_mode="char",
            source_text="aa",
            target_text="a",
            spans=[
                ClassifiedSpan("S-HIGH", 0, 1, Level.SECRET, "first repeated interval"),
                ClassifiedSpan("S-PUBLIC-LOOKALIKE", 1, 2, Level.PUBLIC, "same text, different source/watermark"),
            ],
            editor="editor-repeat",
            parent_version="v1",
        ),
        "classified_watermark_conflict": ReviewCase(
            case_id="classified_watermark_conflict",
            atom_mode="char",
            source_text="aa",
            target_text="a",
            spans=[
                ClassifiedSpan("S-SECRET-X", 0, 1, Level.SECRET, "first source claims SECRET"),
                ClassifiedSpan("S-CONFIDENTIAL-Y", 1, 2, Level.CONFIDENTIAL, "second source claims CONFIDENTIAL"),
            ],
            editor="editor-conflict",
            parent_version="v3",
        ),
        "moved_fragment": ReviewCase(
            case_id="moved_fragment",
            atom_mode="char",
            source_text="ab",
            target_text="ba",
            spans=[ClassifiedSpan("S-MOVE", 0, 1, Level.SECRET, "moved atom")],
            editor="editor-move",
            parent_version="v2",
        ),
        "split_fragment": ReviewCase(
            case_id="split_fragment",
            atom_mode="char",
            source_text="abc",
            target_text="axbyc",
            spans=[ClassifiedSpan("S-SPLIT", 0, 3, Level.SECRET, "split with insertions")],
            editor="editor-split",
            parent_version="v2",
        ),
        "scoped_downgrade_watermark": ReviewCase(
            case_id="scoped_downgrade_watermark",
            atom_mode="char",
            source_text="aa",
            target_text="a",
            spans=[
                ClassifiedSpan("S-DECLARED", 0, 1, Level.SECRET),
                ClassifiedSpan("S-OTHER", 1, 2, Level.SECRET),
            ],
            downgrades=[
                Downgrade(
                    "DG-WATER-1",
                    "S-DECLARED",
                    watermark=Level.INTERNAL,
                    proxy=False,
                    note="caps only its declared source at INTERNAL",
                )
            ],
        ),
        "proxy_downgrade_active": ReviewCase(
            case_id="proxy_downgrade_active",
            atom_mode="char",
            source_text="aa",
            target_text="a",
            spans=[
                ClassifiedSpan("S-PROXY", 0, 1, Level.SECRET),
                ClassifiedSpan("S-LOOKALIKE", 1, 2, Level.PUBLIC),
            ],
            downgrades=[
                Downgrade(
                    "DG-PROXY-1",
                    "S-PROXY",
                    watermark=Level.PUBLIC,
                    proxy=True,
                    note="proxy declaration before revocation",
                )
            ],
        ),
        "proxy_downgrade_revoked": ReviewCase(
            case_id="proxy_downgrade_revoked",
            atom_mode="char",
            source_text="aa",
            target_text="a",
            spans=[
                ClassifiedSpan("S-PROXY", 0, 1, Level.SECRET),
                ClassifiedSpan("S-LOOKALIKE", 1, 2, Level.PUBLIC),
            ],
            downgrades=[
                Downgrade(
                    "DG-PROXY-1",
                    "S-PROXY",
                    watermark=Level.PUBLIC,
                    active=False,
                    proxy=True,
                    revocation_id="REVOKE-PROXY-1",
                    note="proxy declaration was revoked",
                )
            ],
        ),
    }
