from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .scenarios import short_scenarios
from .review import review_case


def _witness_block(title: str, witness: dict[str, Any] | None) -> list[str]:
    if witness is None:
        return [
            f"- {title}: no publication-negative witness; every minimum alignment "
            "still carries some classification."
        ]
    verification = witness["verification"]
    return [
        f"- {title}: target atom `{witness['target_index']}`, "
        f"source atom `{witness['source_index']}`, "
        f"cost `{witness['alignment_cost']}/{witness['minimum_cost']}`, "
        f"paths through edge `{witness['through_count']}/{witness['total_optimal_alignments']}`, "
        f"verified minimum=`{verification['is_minimum']}`.",
        "",
        "```text",
        witness["diagram"],
        "```",
    ]


def render_review_markdown(result: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Review {result['case_id']}")
    lines.append("")
    lines.append(f"Decision: **{result['publication_decision']}**")
    s = result["summary"]
    lines.append(
        f"Optimal cost `{result['alignment']['optimal_cost']}`; "
        f"optimal alignments `{s['optimal_alignment_count']}`; "
        f"exhaustively enumerated `{s['exhaustively_enumerated']}`; "
        f"may atoms `{s['may_sensitive_atoms']}`; "
        f"must atoms `{s['must_sensitive_atoms']}`; "
        f"source-level conflicts `{s['level_conflict_count']}`."
    )
    lines.append("")

    lines.append("## Intervals")
    lines.append("")
    for group_name, intervals in (
        ("Definite/must", result["must_intervals"]),
        ("Possible/may", result["may_intervals"]),
    ):
        lines.append(f"### {group_name}")
        if not intervals:
            lines.append("- none")
            continue
        for interval in intervals:
            lines.append(
                f"- `{interval['interval_id']}` {interval['necessity']} "
                f"char bounds `[{interval['left']}, {interval['right']})` "
                f"text={interval['text']!r} levels={interval['effective_levels']} "
                f"sources={interval['source_ids']} conflicts={len(interval['conflicts'])}"
            )
        lines.append("")

    lines.append("## Hull certificates for moved/copied/split source spans")
    if not result["hull_intervals"]:
        lines.append("- none")
    for hull in result["hull_intervals"]:
        lines.append(
            f"- `{hull['source_id']}` `[{hull['left']}, {hull['right']})` "
            f"text={hull['text']!r} necessity=`{hull['necessity']}` "
            f"support=`{hull['support_count']}/{hull['total_alignment_count']}` "
            f"split=`{hull['split']}` positive=`#{hull['positive_alignment_index']}` "
            f"negative=`#{hull['negative_alignment_index']}`"
        )
    lines.append("")

    lines.append("## Boundary witnesses")
    for interval in result["may_intervals"]:
        lines.append(f"### {interval['interval_id']} `[{interval['left']}, {interval['right']})`")
        lines.extend(_witness_block("positive", interval.get("positive_witness")))
        lines.extend(_witness_block("negative", interval.get("negative_witness")))
        if interval.get("lower_watermark_witness"):
            lines.extend(
                _witness_block(
                    "lower-watermark negative",
                    interval.get("lower_watermark_witness"),
                )
            )
            lines.append(
                f"What the lower witness negates: `{interval['lower_watermark_witness'].get('negates')}`."
            )
        lines.append(f"Negative relation: `{interval['negative_relation']}`")
        lines.append("")

    if result.get("all_optimal_alignments"):
        lines.append("## All minimum alignments")
        for idx, alignment in enumerate(result["all_optimal_alignments"]):
            lines.append(f"### Alignment {idx} (cost {alignment['cost']})")
            lines.append("```text")
            lines.append(alignment["diagram"])
            lines.append("```")
            lines.append(f"Links: `{alignment['links']}`")
            lines.append(
                f"Independent verifier: valid=`{alignment['verification']['valid']}`, "
                f"minimum=`{alignment['verification']['is_minimum']}`"
            )
    return "\n".join(lines) + "\n"


def write_short_reports(out_dir: str | Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scenarios = short_scenarios()
    summary: dict[str, Any] = {"scenarios": {}}
    for name, case in scenarios.items():
        result = review_case(case)
        (out_dir / f"{name}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / f"{name}.md").write_text(
            render_review_markdown(result), encoding="utf-8"
        )
        summary["scenarios"][name] = {
            "decision": result["publication_decision"],
            "optimal_cost": result["alignment"]["optimal_cost"],
            "optimal_alignment_count": result["summary"]["optimal_alignment_count"],
            "may_intervals": [
                [i["left"], i["right"], i["necessity"]]
                for i in result["may_intervals"]
            ],
            "must_intervals": [
                [i["left"], i["right"]] for i in result["must_intervals"]
            ],
            "conflicts": result["summary"]["level_conflict_count"],
        }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "summary.md").write_text(
        "\n".join(
            [
                "# Short alignment scenario summary",
                "",
                "| scenario | decision | cost | #optimal | may intervals | conflicts |",
                "|---|---:|---:|---:|---|---:|",
                *[
                    "| {name} | {decision} | {cost} | {count} | {may} | {conflicts} |".format(
                        name=name,
                        decision=data["decision"],
                        cost=data["optimal_cost"],
                        count=data["optimal_alignment_count"],
                        may=data["may_intervals"],
                        conflicts=data["conflicts"],
                    )
                    for name, data in summary["scenarios"].items()
                ],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return summary
