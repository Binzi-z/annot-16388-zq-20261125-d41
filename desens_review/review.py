from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .align import (
    Alignment,
    AlignmentCosts,
    Lattice,
    TargetChoice,
    verify_alignment,
)
from .model import (
    Atom,
    ClassifiedSpan,
    Downgrade,
    Level,
    ReviewCase,
    source_indices_for_span,
)
from .transport import TransportLattice, enumerate_transport_alignments


class ReviewResult(dict):
    """JSON-serializable review report."""


def make_lattice(
    model: str,
    source_atoms: list[Atom],
    target_atoms: list[Atom],
    costs: AlignmentCosts,
):
    if model == "transport":
        return TransportLattice(source_atoms, target_atoms, costs)
    if model == "ordered":
        return Lattice(source_atoms, target_atoms, costs)
    raise ValueError(f"unknown alignment model {model!r}")


@dataclass(frozen=True)
class LabelAtSource:
    source_id: str
    raw_level: int
    effective_level: int
    span_note: str
    downgrade_id: str | None = None
    watermark: int | None = None


def downgrade_audit(
    spans: list[ClassifiedSpan], downgrades: list[Downgrade]
) -> list[dict[str, Any]]:
    source_ids = {s.source_id for s in spans}
    audit: list[dict[str, Any]] = []
    for dg in downgrades:
        applies = dg.source_id in source_ids
        active = dg.active and not dg.revocation_id
        if not applies:
            effect = "source_mismatch_no_effect"
        elif not active:
            effect = "revoked_no_effect"
        else:
            effect = "active_watermark_cap"
        audit.append(
            {
                "decl_id": dg.decl_id,
                "source_id": dg.source_id,
                "watermark": int(dg.watermark),
                "active": bool(active),
                "proxy": dg.proxy,
                "revocation_id": dg.revocation_id,
                "declared_source_present": applies,
                "effect": effect,
                "note": dg.note,
            }
        )
    return audit


def labels_by_source_atom(case: ReviewCase, source_atoms: list[Atom]) -> dict[int, list[LabelAtSource]]:
    audit = downgrade_audit(case.spans, case.downgrades)
    active_downgrades: dict[str, list[Downgrade]] = {}
    for dg in case.downgrades:
        if dg.active and not dg.revocation_id:
            active_downgrades.setdefault(dg.source_id, []).append(dg)

    result: dict[int, list[LabelAtSource]] = {}
    for span in case.spans:
        matching = active_downgrades.get(span.source_id, [])
        if matching:
            # Several explicit caps may exist; the lowest watermark is the
            # conservative effective cap.  Audit retains every declaration.
            chosen = min(matching, key=lambda d: (d.watermark, d.decl_id))
            effective = min(int(span.level), int(chosen.watermark))
            dg_id = chosen.decl_id
            watermark = int(chosen.watermark)
        else:
            effective = int(span.level)
            dg_id = None
            watermark = None

        for index in source_indices_for_span(span, source_atoms):
            result.setdefault(index, []).append(
                LabelAtSource(
                    source_id=span.source_id,
                    raw_level=int(span.level),
                    effective_level=effective,
                    span_note=span.note,
                    downgrade_id=dg_id,
                    watermark=watermark,
                )
            )
    return result


def _choice_risk(
    choice: TargetChoice, labels: dict[int, list[LabelAtSource]]
) -> dict[str, Any]:
    provs: list[dict[str, Any]] = []
    level = int(Level.PUBLIC)
    if choice.kind == "link" and choice.source_index is not None:
        for label in labels.get(choice.source_index, []):
            provs.append(
                {
                    "source_id": label.source_id,
                    "source_index": choice.source_index,
                    "raw_level": label.raw_level,
                    "effective_level": label.effective_level,
                    "downgrade_id": label.downgrade_id,
                    "watermark": label.watermark,
                    "note": label.span_note,
                }
            )
            level = max(level, label.effective_level)

    effective_levels = sorted({p["effective_level"] for p in provs})
    raw_levels = sorted({p["raw_level"] for p in provs})
    return {
        **choice.to_dict(),
        "effective_level": level,
        "provenances": provs,
        "label_conflict": len(effective_levels) > 1 or len(raw_levels) > 1,
    }


def hulls_for_alignment(
    alignment: Alignment,
    case: ReviewCase,
    source_atoms: list[Atom],
    target_atoms: list[Atom],
    labels: dict[int, list[LabelAtSource]],
) -> list[dict[str, Any]]:
    hulls: list[dict[str, Any]] = []
    links_by_source: dict[int, int] = dict(alignment.links)

    for span in case.spans:
        atom_ids = source_indices_for_span(span, source_atoms)
        linked = [
            (s, links_by_source[s])
            for s in sorted(atom_ids)
            if s in links_by_source
        ]
        if not linked:
            continue

        target_ids = [t for _, t in linked]
        first_t, last_t = min(target_ids), max(target_ids)
        linked_target_set = {t for _, t in linked}
        gaps = [
            t
            for t in range(first_t, last_t + 1)
            if t not in linked_target_set
        ]
        span_labels = [
            label
            for s in atom_ids
            for label in labels.get(s, [])
            if label.source_id == span.source_id
        ]
        effective = max((x.effective_level for x in span_labels), default=int(span.level))
        hulls.append(
            {
                "source_id": span.source_id,
                "raw_level": int(span.level),
                "effective_level": effective,
                "left": target_atoms[first_t].start,
                "right": target_atoms[last_t].end,
                "first_target_index": first_t,
                "last_target_index": last_t,
                "split": len(gaps) > 0 or len(linked) < len(atom_ids),
                "gap_target_indices": gaps,
                "pieces": [
                    {
                        "source_index": s,
                        "target_index": t,
                        "left": target_atoms[t].start,
                        "right": target_atoms[t].end,
                        "text": target_atoms[t].text,
                    }
                    for s, t in linked
                ],
            }
        )
    hulls.sort(key=lambda h: (h["left"], h["right"], h["source_id"]))
    return hulls


def _witness_dict(
    polarity: str,
    choice: dict[str, Any],
    lattice: Lattice,
    case: ReviewCase,
    source_atoms: list[Atom],
    target_atoms: list[Atom],
    labels: dict[int, list[LabelAtSource]],
) -> dict[str, Any]:
    raw_choice = TargetChoice(
        target_index=choice["target_index"],
        kind=choice["kind"],
        edge_i=choice["edge_i"],
        source_index=choice["source_index"],
        through_cost=choice["through_cost"],
        through_count=choice["through_count"],
    )
    alignment = lattice.witness_for_choice(raw_choice)
    verification = lattice.verify_alignment(alignment)
    return {
        "polarity": polarity,
        "target_index": choice["target_index"],
        "kind": choice["kind"],
        "source_index": choice["source_index"],
        "edge_i": choice["edge_i"],
        "minimum_cost": lattice.total_cost,
        "alignment_cost": alignment.cost,
        "through_count": choice["through_count"],
        "total_optimal_alignments": lattice.total_paths,
        "ops": [op.to_dict() for op in alignment.ops],
        "diagram": lattice.diagram(alignment),
        "verification": verification,
        "source_hulls": hulls_for_alignment(
            alignment, case, source_atoms, target_atoms, labels
        ),
    }


def _max_choice(atom: dict[str, Any]) -> dict[str, Any]:
    return max(
        atom["choices"],
        key=lambda ch: (
            ch["effective_level"],
            0 if ch["kind"] == "link" else -1,
            -int(ch["source_index"] if ch["source_index"] is not None else 10**9),
            ch["through_count"],
        ),
    )


def _min_choice(atom: dict[str, Any]) -> dict[str, Any]:
    return min(
        atom["choices"],
        key=lambda ch: (
            ch["effective_level"],
            0 if ch["kind"] == "insert" else -1,
            int(ch["source_index"] if ch["source_index"] is not None else -1),
            -ch["through_count"],
        ),
    )


def _interval_records(
    status: str,
    atom_risks: list[dict[str, Any]],
    target_atoms: list[Atom],
    publish_max_level: int,
    lattice: Lattice,
    case: ReviewCase,
    source_atoms: list[Atom],
    labels: dict[int, list[LabelAtSource]],
    include_witnesses: bool,
) -> list[dict[str, Any]]:
    if status == "must":
        predicate = lambda a: a["must_level"] > publish_max_level  # noqa: E731
        interval_id = "MUST"
    else:
        predicate = lambda a: a["may_level"] > publish_max_level  # noqa: E731
        interval_id = "MAY"

    records: list[dict[str, Any]] = []
    m = len(atom_risks)
    pos = 0
    serial = 1
    while pos < m:
        if not predicate(atom_risks[pos]):
            pos += 1
            continue
        start = pos
        while pos + 1 < m and predicate(atom_risks[pos + 1]):
            pos += 1
        end = pos
        atoms = target_atoms[start : end + 1]
        left, right = atoms[0].start, atoms[-1].end

        interval_choices = [
            ch for a in atom_risks[start : end + 1] for ch in a["choices"]
        ]
        positive_choice = max(
            interval_choices,
            key=lambda ch: (
                ch["effective_level"],
                0 if ch["kind"] == "link" else -1,
                ch["through_count"],
            ),
        )
        lowest_watermark_choice = min(
            interval_choices, key=lambda ch: ch["effective_level"]
        )
        negative_choice = lowest_watermark_choice
        negative_relation = "same_interval_atom"
        if negative_choice["effective_level"] > publish_max_level:
            negative_choice = None
            if start > 0:
                outside_atom = atom_risks[start - 1]
                negative_choice = _min_choice(outside_atom)
                negative_relation = "outside_left_boundary"
            elif end + 1 < m:
                outside_atom = atom_risks[end + 1]
                negative_choice = _min_choice(outside_atom)
                negative_relation = "outside_right_boundary"
            else:
                negative_relation = "no_publication_negative_alignment_exists"

        levels = sorted(
            {
                ch["effective_level"]
                for ch in interval_choices
                if ch["effective_level"] > Level.PUBLIC
            }
        )
        source_ids = sorted(
            {
                p["source_id"]
                for ch in interval_choices
                for p in ch["provenances"]
            }
        )
        conflicts = []
        for a in atom_risks[start : end + 1]:
            link_levels = sorted(
                {
                    p["effective_level"]
                    for ch in a["choices"]
                    for p in ch["provenances"]
                    if ch["kind"] == "link"
                }
            )
            all_levels = sorted({ch["effective_level"] for ch in a["choices"]})
            source_ids_atom = sorted(
                {p["source_id"] for ch in a["choices"] for p in ch["provenances"]}
            )
            if len(link_levels) > 1:
                conflicts.append(
                    {
                        "target_index": a["index"],
                        "type": "two_source_level_conflict",
                        "effective_levels": link_levels,
                        "source_ids": source_ids_atom,
                    }
                )
            elif a["may_level"] > publish_max_level and a["must_level"] <= publish_max_level:
                conflicts.append(
                    {
                        "target_index": a["index"],
                        "type": "sensitive_link_versus_public_or_insertion",
                        "candidate_levels": all_levels,
                        "source_ids": source_ids_atom,
                    }
                )

        all_definite = all(
            a["must_level"] > publish_max_level for a in atom_risks[start : end + 1]
        )
        record: dict[str, Any] = {
            "interval_id": f"{interval_id}-{serial}",
            "status": status,
            "necessity": "definite" if all_definite else "possible",
            "atom_start": start,
            "atom_end_inclusive": end,
            "left": left,
            "right": right,
            "text": case.target_text[left:right],
            "effective_levels": levels,
            "max_level": max(levels, default=int(Level.PUBLIC)),
            "source_ids": source_ids,
            "conflicts": conflicts,
            "negative_relation": negative_relation,
        }
        if include_witnesses:
            record["positive_witness"] = _witness_dict(
                "positive",
                positive_choice,
                lattice,
                case,
                source_atoms,
                target_atoms,
                labels,
            )
            record["lower_watermark_witness"] = _witness_dict(
                "lower_watermark_negative",
                lowest_watermark_choice,
                lattice,
                case,
                source_atoms,
                target_atoms,
                labels,
            )
            record["lower_watermark_witness"]["negates"] = (
                "publication_sensitivity"
                if lowest_watermark_choice["effective_level"] <= publish_max_level
                else "higher_watermark_only_interval_remains_classified"
            )
            if negative_choice is not None:
                record["negative_witness"] = _witness_dict(
                    "negative",
                    negative_choice,
                    lattice,
                    case,
                    source_atoms,
                    target_atoms,
                    labels,
                )
            else:
                record["negative_witness"] = None
        records.append(record)
        serial += 1
        pos = end + 1
    return records


def review_case(
    case: ReviewCase,
    *,
    publish_max_level: int = Level.PUBLIC,
    include_witnesses: bool = True,
    enumeration_limit: int = 200,
    costs: AlignmentCosts | None = None,
    alignment_model: str | None = None,
) -> ReviewResult:
    """Compute must/may intervals and auditable witnesses for one case."""

    costs = costs or AlignmentCosts()
    model_name = alignment_model or case.alignment_model
    source_atoms = case.atoms("source")
    target_atoms = case.atoms("target")
    labels = labels_by_source_atom(case, source_atoms)
    lattice = make_lattice(model_name, source_atoms, target_atoms, costs)
    choices_by_target = lattice.choices_for_targets()

    atom_risks: list[dict[str, Any]] = []
    for target_index, choices in enumerate(choices_by_target):
        enriched = [_choice_risk(ch, labels) for ch in choices]
        may_level = max(ch["effective_level"] for ch in enriched)
        must_level = min(ch["effective_level"] for ch in enriched)
        atom = target_atoms[target_index]
        atom_risks.append(
            {
                "index": target_index,
                "text": atom.text,
                "left": atom.start,
                "right": atom.end,
                "may_level": may_level,
                "must_level": must_level,
                "may_sensitive": may_level > publish_max_level,
                "must_sensitive": must_level > publish_max_level,
                "choice_count": len(enriched),
                "choices": enriched,
            }
        )

    must_intervals = _interval_records(
        "must",
        atom_risks,
        target_atoms,
        publish_max_level,
        lattice,
        case,
        source_atoms,
        labels,
        include_witnesses,
    )
    may_intervals = _interval_records(
        "may",
        atom_risks,
        target_atoms,
        publish_max_level,
        lattice,
        case,
        source_atoms,
        labels,
        include_witnesses,
    )

    exhaustive_alignments: list[dict[str, Any]] | None = None
    hull_certificates: list[dict[str, Any]] = []
    if lattice.total_paths <= enumeration_limit:
        exhaustive_alignments = []
        if model_name == "transport":
            all_alignments = enumerate_transport_alignments(
                source_atoms, target_atoms, costs
            )
        else:
            all_alignments = enumerate_optimal_alignments(
                source_atoms, target_atoms, costs
            )

        for alignment in all_alignments:
            exhaustive_alignments.append(
                {
                    "cost": alignment.cost,
                    "ops": [op.to_dict() for op in alignment.ops],
                    "links": alignment.links,
                    "diagram": lattice.diagram(alignment),
                    "source_hulls": hulls_for_alignment(
                        alignment, case, source_atoms, target_atoms, labels
                    ),
                    "verification": lattice.verify_alignment(alignment),
                }
            )

        hull_map: dict[tuple[str, int, int], dict[str, Any]] = {}
        hull_keys_by_alignment: list[set[tuple[str, int, int]]] = []
        for alignment_index, alignment_record in enumerate(exhaustive_alignments):
            keys = set()
            for hull in alignment_record["source_hulls"]:
                key = (hull["source_id"], hull["left"], hull["right"])
                keys.add(key)
                entry = hull_map.setdefault(
                    key,
                    {
                        "source_id": hull["source_id"],
                        "left": hull["left"],
                        "right": hull["right"],
                        "text": case.target_text[hull["left"] : hull["right"]],
                        "raw_level": hull["raw_level"],
                        "effective_level": hull["effective_level"],
                        "split": hull["split"],
                        "support_count": 0,
                        "total_alignment_count": lattice.total_paths,
                        "positive_alignment_index": alignment_index,
                        "pieces": hull["pieces"],
                    },
                )
                entry["support_count"] += 1
            hull_keys_by_alignment.append(keys)

        for key, entry in hull_map.items():
            negative_index = next(
                (
                    idx
                    for idx, keys in enumerate(hull_keys_by_alignment)
                    if key not in keys
                ),
                None,
            )
            entry["necessity"] = (
                "definite"
                if entry["support_count"] == lattice.total_paths
                else "possible"
            )
            entry["negative_alignment_index"] = negative_index
            hull_certificates.append(entry)
        hull_certificates.sort(key=lambda h: (h["left"], h["right"], h["source_id"]))

    may_count = sum(a["may_sensitive"] for a in atom_risks)
    must_count = sum(a["must_sensitive"] for a in atom_risks)
    blocked = bool(may_intervals)
    result = ReviewResult(
        {
            "case_id": case.case_id,
            "atom_mode": case.atom_mode,
            "alignment_model": model_name,
            "editor": case.editor,
            "parent_version": case.parent_version,
            "publication_decision": "BLOCK_POSSIBLE_SENSITIVE" if blocked else "RELEASE",
            "publish_max_level": int(publish_max_level),
            "alignment": lattice.marker_summary(),
            "downgrade_audit": downgrade_audit(case.spans, case.downgrades),
            "source_text": case.source_text,
            "target_text": case.target_text,
            "atom_risks": atom_risks if include_witnesses else [],
            "must_intervals": must_intervals,
            "may_intervals": may_intervals,
            "hull_intervals": hull_certificates,
            "summary": {
                "target_atoms": len(target_atoms),
                "may_sensitive_atoms": may_count,
                "must_sensitive_atoms": must_count,
                "must_interval_count": len(must_intervals),
                "may_interval_count": len(may_intervals),
                "optimal_alignment_count": lattice.total_paths,
                "exhaustively_enumerated": exhaustive_alignments is not None,
                "level_conflict_count": sum(
                    1
                    for interval in may_intervals
                    for conflict in interval["conflicts"]
                    if conflict["type"] == "two_source_level_conflict"
                ),
            },
        }
    )
    if exhaustive_alignments is not None:
        result["all_optimal_alignments"] = exhaustive_alignments
    return result


def compact_markers(case: ReviewCase, *, publish_max_level: int = Level.PUBLIC) -> dict[str, Any]:
    """Low-allocation marker record used by the 50k-paragraph corpus."""

    source_atoms = case.atoms("source")
    target_atoms = case.atoms("target")
    labels = labels_by_source_atom(case, source_atoms)
    lattice = make_lattice(case.alignment_model, source_atoms, target_atoms, AlignmentCosts())
    choices = lattice.choices_for_targets()

    may_targets: list[int] = []
    must_targets: list[int] = []
    may_intervals: list[list[int]] = []
    must_intervals: list[list[int]] = []
    conflict_targets: list[int] = []

    atom_levels: list[tuple[int, int]] = []
    for j, target_choices in enumerate(choices):
        levels: list[int] = []
        link_levels: list[int] = []
        for ch in target_choices:
            level = int(Level.PUBLIC)
            if ch.kind == "link":
                for label in labels.get(ch.source_index or -1, []):
                    level = max(level, label.effective_level)
                    link_levels.append(label.effective_level)
            levels.append(level)
        may_level = max(levels)
        must_level = min(levels)
        atom_levels.append((may_level, must_level))
        if may_level > publish_max_level:
            may_targets.append(j)
        if must_level > publish_max_level:
            must_targets.append(j)
        if len(set(link_levels)) > 1:
            conflict_targets.append(j)

    def char_ranges(indices: list[int]) -> list[list[int]]:
        ranges: list[list[int]] = []
        for idx in indices:
            if not ranges or idx != ranges[-1][3] + 1:
                atom = target_atoms[idx]
                ranges.append([atom.start, atom.end, idx, idx])
            else:
                atom = target_atoms[idx]
                ranges[-1][1] = atom.end
                ranges[-1][3] = idx
        return [[left, right] for left, right, _, _ in ranges]

    may_intervals = char_ranges(may_targets)
    must_intervals = char_ranges(must_targets)
    summary = lattice.marker_summary()
    return {
        "case_id": case.case_id,
        "source_chars": len(case.source_text),
        "target_chars": len(case.target_text),
        **summary,
        "may_targets": may_targets,
        "must_targets": must_targets,
        "may_intervals": may_intervals,
        "must_intervals": must_intervals,
        "conflict_targets": conflict_targets,
        "decision": "BLOCK" if may_targets else "RELEASE",
    }
