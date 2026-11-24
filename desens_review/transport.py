from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import factorial
from typing import Sequence

from .align import Alignment, AlignmentCosts, Op, TargetChoice
from .model import Atom


def _perm(pool: int, choose: int) -> int:
    if choose < 0 or choose > pool:
        return 0
    return factorial(pool) // factorial(pool - choose)


def verify_transport_alignment(
    source: Sequence[Atom],
    target: Sequence[Atom],
    alignment: Alignment,
    costs: AlignmentCosts = AlignmentCosts(),
) -> dict:
    """Verify a crossing-tolerant one-to-one retention alignment."""

    errors: list[str] = []
    used_sources: set[int] = set()
    used_targets: set[int] = set()
    computed_cost = 0

    for pos, op in enumerate(alignment.ops):
        computed_cost += op.cost
        if op.kind == "delete":
            i = op.source_index
            if i is None or not 0 <= i < len(source):
                errors.append(f"op {pos}: bad delete source index")
                continue
            if i in used_sources:
                errors.append(f"op {pos}: source {i} used twice")
            used_sources.add(i)
            if op.target_index is not None:
                errors.append(f"op {pos}: delete has target index")
            if op.cost != costs.delete_source:
                errors.append(f"op {pos}: bad delete cost")
        elif op.kind == "insert":
            j = op.target_index
            if j is None or not 0 <= j < len(target):
                errors.append(f"op {pos}: bad insert target index")
                continue
            if j in used_targets:
                errors.append(f"op {pos}: target {j} used twice")
            used_targets.add(j)
            if op.source_index is not None:
                errors.append(f"op {pos}: insert has source index")
            if op.cost != costs.insert_target:
                errors.append(f"op {pos}: bad insert cost")
        elif op.kind in {"match", "sub"}:
            i, j = op.source_index, op.target_index
            if i is None or j is None:
                errors.append(f"op {pos}: link missing endpoint")
                continue
            if not 0 <= i < len(source) or not 0 <= j < len(target):
                errors.append(f"op {pos}: link index out of range")
                continue
            if i in used_sources:
                errors.append(f"op {pos}: source {i} linked twice")
            if j in used_targets:
                errors.append(f"op {pos}: target {j} linked twice")
            used_sources.add(i)
            used_targets.add(j)
            expected = costs.substitution(source[i], target[j])
            expected_kind = "match" if expected == costs.match else "sub"
            if op.kind != expected_kind:
                errors.append(f"op {pos}: kind {op.kind} != {expected_kind}")
            if op.cost != expected:
                errors.append(f"op {pos}: cost {op.cost} != {expected}")
        else:
            errors.append(f"op {pos}: unknown kind {op.kind}")

    missing_sources = set(range(len(source))) - used_sources
    missing_targets = set(range(len(target))) - used_targets
    if missing_sources:
        errors.append(f"source atoms without link/delete: {sorted(missing_sources)}")
    if missing_targets:
        errors.append(f"target atoms without link/insert: {sorted(missing_targets)}")

    optimum = TransportLattice(source, target, costs).total_cost
    is_minimum = not errors and computed_cost == optimum
    if not errors and alignment.cost != computed_cost:
        errors.append(f"declared cost {alignment.cost} != computed {computed_cost}")
    if not is_minimum and not any("optimum" in e for e in errors):
        if computed_cost != optimum:
            errors.append(f"alignment cost {computed_cost} is not transport optimum {optimum}")

    return {
        "valid": not errors,
        "is_minimum": is_minimum,
        "computed_cost": computed_cost,
        "optimum_cost": optimum,
        "errors": errors,
        "model": "transport_reorder",
    }


def transport_diagram(
    source: Sequence[Atom], target: Sequence[Atom], alignment: Alignment
) -> str:
    lines = [
        "Source atoms: " + "  ".join(f"{i}:{a.text}" for i, a in enumerate(source)),
        "Target atoms: " + "  ".join(f"{j}:{a.text}" for j, a in enumerate(target)),
        "Operations (crossing links are allowed):",
    ]
    for op in alignment.ops:
        if op.kind == "match":
            lines.append(f"  S{op.source_index}[{source[op.source_index].text}] "
                         f"== T{op.target_index}[{target[op.target_index].text}]  cost=0")
        elif op.kind == "sub":
            lines.append(f"  S{op.source_index}[{source[op.source_index].text}] "
                         f"~~ T{op.target_index}[{target[op.target_index].text}]  cost=1")
        elif op.kind == "delete":
            lines.append(f"  S{op.source_index}[{source[op.source_index].text}] -> delete  cost=1")
        else:
            lines.append(f"  insert -> T{op.target_index}[{target[op.target_index].text}]  cost=1")
    return "\n".join(lines)


class TransportLattice:
    """All optimal one-to-one alignments with arbitrary atom reordering.

    This is the move/copy/split-aware counterpart of the ordered Levenshtein
    lattice.  Equal atoms may link across arbitrary distances; repeated values
    create occurrence-choice ambiguity.
    """

    model_name = "transport_reorder"

    def __init__(
        self,
        source: Sequence[Atom],
        target: Sequence[Atom],
        costs: AlignmentCosts = AlignmentCosts(),
    ) -> None:
        if costs != AlignmentCosts():
            raise ValueError("TransportLattice currently supports default unit costs")
        self.source = list(source)
        self.target = list(target)
        self.costs = costs
        self.n = len(source)
        self.m = len(target)

        self.source_by_text: dict[str, list[int]] = defaultdict(list)
        self.target_by_text: dict[str, list[int]] = defaultdict(list)
        for i, atom in enumerate(self.source):
            self.source_by_text[atom.text].append(i)
        for j, atom in enumerate(self.target):
            self.target_by_text[atom.text].append(j)

        texts = set(self.source_by_text) | set(self.target_by_text)
        self.source_counts = {t: len(self.source_by_text.get(t, ())) for t in texts}
        self.target_counts = {t: len(self.target_by_text.get(t, ())) for t in texts}
        self.exact_count = sum(
            min(self.source_counts[t], self.target_counts[t]) for t in texts
        )
        self.total_cost = max(self.n, self.m) - self.exact_count

        self.source_excess = {
            i
            for t, ids in self.source_by_text.items()
            if self.source_counts[t] > self.target_counts[t]
            for i in ids
        }
        self.target_excess = {
            j
            for t, ids in self.target_by_text.items()
            if self.target_counts[t] > self.source_counts[t]
            for j in ids
        }
        self.remaining_sources = self.n - self.exact_count
        self.remaining_targets = self.m - self.exact_count
        self.exact_matchings_per_text = {
            t: _perm(max(self.source_counts[t], self.target_counts[t]),
                     min(self.source_counts[t], self.target_counts[t]))
            for t in texts
            if min(self.source_counts[t], self.target_counts[t]) > 0
        }
        self.exact_alignment_count = 1
        for count in self.exact_matchings_per_text.values():
            self.exact_alignment_count *= count

        rs, rt = self.remaining_sources, self.remaining_targets
        if rs <= rt:
            self.substitution_alignment_count = _perm(rt, rs)
        else:
            self.substitution_alignment_count = _perm(rs, rt)
        self.total_paths = (
            self.exact_alignment_count * self.substitution_alignment_count
        )
        self._choices: list[list[TargetChoice]] | None = None

    def verify_alignment(self, alignment: Alignment) -> dict:
        return verify_transport_alignment(
            self.source, self.target, alignment, self.costs
        )

    def diagram(self, alignment: Alignment) -> str:
        return transport_diagram(self.source, self.target, alignment)

    def choices_for_targets(self) -> list[list[TargetChoice]]:
        if self._choices is not None:
            return self._choices
        choices_by_target: list[list[TargetChoice]] = [[] for _ in range(self.m)]
        exact_other_product_cache: dict[str, int] = {}

        def exact_other_product(text: str) -> int:
            if text not in exact_other_product_cache:
                value = self.exact_alignment_count
                if text in self.exact_matchings_per_text:
                    value //= self.exact_matchings_per_text[text]
                exact_other_product_cache[text] = value
            return exact_other_product_cache[text]

        for j, atom in enumerate(self.target):
            text = atom.text
            s_count = self.source_counts[text]
            t_count = self.target_counts[text]

            # Exact retention choices.
            if s_count:
                edge_text_matchings = _perm(
                    max(s_count, t_count) - 1, min(s_count, t_count) - 1
                )
                through = (
                    edge_text_matchings
                    * exact_other_product(text)
                    * self.substitution_alignment_count
                )
                for i in self.source_by_text[text]:
                    choices_by_target[j].append(
                        TargetChoice(j, "link", i, i, self.total_cost, through)
                    )

            # Substitution retention choices.  Only excess occurrences may be
            # left out of the mandatory maximum exact matching.
            if j in self.target_excess and self.source_excess:
                rs, rt = self.remaining_sources, self.remaining_targets
                sub_edge_ways = _perm(max(rs, rt) - 1, min(rs, rt) - 1)
                for i in sorted(self.source_excess):
                    source_text = self.source[i].text
                    if source_text == text:
                        continue

                    # The fixed excess endpoints must both be excluded from
                    # their text-specific maximum exact matchings.
                    exact_ways = 1
                    for other_text in set(self.source_counts) | set(self.target_counts):
                        s_count = self.source_counts[other_text]
                        t_count = self.target_counts[other_text]
                        minimum = min(s_count, t_count)
                        if other_text == source_text:
                            text_ways = _perm(s_count - 1, t_count)
                        elif other_text == text:
                            text_ways = _perm(t_count - 1, s_count)
                        elif minimum:
                            text_ways = self.exact_matchings_per_text[other_text]
                        else:
                            text_ways = 1
                        exact_ways *= text_ways

                    through = exact_ways * sub_edge_ways
                    choices_by_target[j].append(
                        TargetChoice(j, "link", i, i, self.total_cost, through)
                    )

            # Insertion choices when there are more targets than sources.
            if self.m > self.n and j in self.target_excess:
                exact_ways = 1
                for other_text in set(self.source_counts) | set(self.target_counts):
                    s_count = self.source_counts[other_text]
                    t_count = self.target_counts[other_text]
                    minimum = min(s_count, t_count)
                    if other_text == text:
                        text_ways = _perm(t_count - 1, s_count)
                    elif minimum:
                        text_ways = self.exact_matchings_per_text[other_text]
                    else:
                        text_ways = 1
                    exact_ways *= text_ways
                through = exact_ways * _perm(
                    self.remaining_targets - 1, self.remaining_sources
                )
                choices_by_target[j].append(
                    TargetChoice(j, "insert", -1, None, self.total_cost, through)
                )

        for choices in choices_by_target:
            choices.sort(
                key=lambda ch: (
                    0 if ch.kind == "link" else 1,
                    ch.source_index if ch.source_index is not None else 10**9,
                )
            )
        self._choices = choices_by_target
        return choices_by_target

    def witness_for_choice(self, choice: TargetChoice) -> Alignment:
        forced_link: tuple[int, int, str, int] | None = None
        inserted_target: int | None = None
        if choice.kind == "insert":
            inserted_target = choice.target_index
        elif choice.source_index is not None:
            i, j = choice.source_index, choice.target_index
            sub_cost = self.costs.substitution(self.source[i], self.target[j])
            kind = "match" if sub_cost == self.costs.match else "sub"
            forced_link = (i, j, kind, sub_cost)

        used_sources: set[int] = set()
        used_targets: set[int] = set()
        links: list[tuple[int, int, str, int]] = []
        insertions: list[int] = []

        if forced_link is not None:
            i, j, kind, cost = forced_link
            links.append(forced_link)
            used_sources.add(i)
            used_targets.add(j)
        if inserted_target is not None:
            insertions.append(inserted_target)
            used_targets.add(inserted_target)

        # Build a maximum exact matching by atom text.
        for text, source_ids in sorted(self.source_by_text.items()):
            target_ids = self.target_by_text.get(text, [])
            need = min(len(source_ids), len(target_ids))
            existing = sum(
                1
                for i, j, kind, _ in links
                if kind == "match"
                and i in self.source_by_text.get(text, [])
                and j in self.target_by_text.get(text, [])
            )
            need -= existing
            available_sources = [i for i in source_ids if i not in used_sources]
            available_targets = [j for j in target_ids if j not in used_targets]
            for i, j in zip(available_sources[:need], available_targets[:need]):
                links.append((i, j, "match", self.costs.match))
                used_sources.add(i)
                used_targets.add(j)

        # Pair all atoms on the smaller remaining side by substitution.
        remaining_sources = [i for i in range(self.n) if i not in used_sources]
        remaining_targets = [j for j in range(self.m) if j not in used_targets]
        pair_count = min(len(remaining_sources), len(remaining_targets))
        for i, j in zip(remaining_sources[:pair_count], remaining_targets[:pair_count]):
            cost = self.costs.substitution(self.source[i], self.target[j])
            kind = "match" if cost == self.costs.match else "sub"
            links.append((i, j, kind, cost))
            used_sources.add(i)
            used_targets.add(j)

        ops: list[Op] = []
        # Target-ordered output makes boundary certificates easy to read.
        target_to_link = {j: (i, kind, cost) for i, j, kind, cost in links}
        for j in range(self.m):
            if j in target_to_link:
                i, kind, cost = target_to_link[j]
                ops.append(Op(kind, i, j, cost))
            else:
                # Every non-linked target is inserted, including an insertion
                # edge forced by the witness certificate.
                ops.append(Op("insert", None, j, self.costs.insert_target))
        for i in range(self.n):
            if i not in used_sources:
                ops.append(Op("delete", i, None, self.costs.delete_source))
                used_sources.add(i)

        alignment = Alignment(ops, self.total_cost)
        verdict = self.verify_alignment(alignment)
        if not verdict["valid"] or not verdict["is_minimum"]:
            raise RuntimeError(f"constructed invalid transport witness: {verdict['errors']}")
        return alignment

    def marker_summary(self) -> dict:
        choices = self.choices_for_targets()
        may_links: list[list[int]] = []
        must_links: list[list[int]] = []
        for target_index, target_choices in enumerate(choices):
            for ch in target_choices:
                if ch.kind != "link" or ch.source_index is None:
                    continue
                may_links.append([ch.source_index, target_index])
                if ch.through_count == self.total_paths:
                    must_links.append([ch.source_index, target_index])
        return {
            "model": self.model_name,
            "source_atoms": self.n,
            "target_atoms": self.m,
            "dp_cells": self.n * self.m,
            "optimal_cost": self.total_cost,
            "optimal_path_count": self.total_paths,
            "may_links": may_links,
            "must_links": must_links,
            "choice_count": sum(len(x) for x in choices),
        }


def enumerate_transport_alignments(
    source: Sequence[Atom],
    target: Sequence[Atom],
    costs: AlignmentCosts = AlignmentCosts(),
) -> list[Alignment]:
    """Enumerate every minimum transport alignment for short strings."""

    lattice = TransportLattice(source, target, costs)
    text_values = sorted(set(lattice.source_by_text) | set(lattice.target_by_text))

    def exact_matchings_for_text(text: str) -> list[list[tuple[int, int]]]:
        ss = lattice.source_by_text.get(text, [])
        tt = lattice.target_by_text.get(text, [])
        k = min(len(ss), len(tt))
        if k == 0:
            return [[]]
        if len(ss) <= len(tt):
            # Every source is used; choose an ordered injection into targets.
            results = []
            for target_perm in _permutations(tt, len(ss)):
                results.append(list(zip(ss, target_perm)))
            return results
        # Every target is used; choose an ordered injection of sources.
        results = []
        for source_perm in _permutations(ss, len(tt)):
            results.append(list(zip(source_perm, tt)))
        return results

    all_text_matchings = [exact_matchings_for_text(t) for t in text_values]
    results: list[Alignment] = []

    for exact_groups in _product_lists(all_text_matchings):
        exact_links = [pair for group in exact_groups for pair in group]
        used_sources = {i for i, _ in exact_links}
        used_targets = {j for _, j in exact_links}
        rem_sources = [i for i in range(lattice.n) if i not in used_sources]
        rem_targets = [j for j in range(lattice.m) if j not in used_targets]

        if len(rem_sources) <= len(rem_targets):
            sub_options = [
                list(zip(rem_sources, chosen_targets))
                for chosen_targets in _permutations(rem_targets, len(rem_sources))
            ]
        else:
            sub_options = [
                list(zip(chosen_sources, rem_targets))
                for chosen_sources in _permutations(rem_sources, len(rem_targets))
            ]

        for sub_pairs in sub_options:
            links = [(i, j, "match", costs.match) for i, j in exact_links]
            used_s = {i for i, _ in exact_links}
            used_t = {j for _, j in exact_links}
            for i, j in sub_pairs:
                cost = costs.substitution(source[i], target[j])
                kind = "match" if cost == costs.match else "sub"
                links.append((i, j, kind, cost))
                used_s.add(i)
                used_t.add(j)

            target_to_link = {j: (i, kind, cost) for i, j, kind, cost in links}
            ops: list[Op] = []
            for j in range(lattice.m):
                if j in target_to_link:
                    i, kind, cost = target_to_link[j]
                    ops.append(Op(kind, i, j, cost))
                else:
                    ops.append(Op("insert", None, j, costs.insert_target))
            for i in range(lattice.n):
                if i not in used_s:
                    ops.append(Op("delete", i, None, costs.delete_source))

            alignment = Alignment(ops, lattice.total_cost)
            verdict = lattice.verify_alignment(alignment)
            if not verdict["valid"] or not verdict["is_minimum"]:
                raise RuntimeError(verdict["errors"])
            results.append(alignment)

    return results


def _permutations(values: list[int], choose: int):
    from itertools import permutations

    yield from permutations(values, choose)


def _product_lists(groups: list[list]):
    from itertools import product

    yield from product(*groups)
