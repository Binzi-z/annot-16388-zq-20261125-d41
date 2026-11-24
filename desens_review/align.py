from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Callable, Iterator, Sequence

from .model import Atom


@dataclass(frozen=True)
class AlignmentCosts:
    match: int = 0
    mismatch: int = 1
    delete_source: int = 1
    insert_target: int = 1

    def substitution(self, source_atom: Atom, target_atom: Atom) -> int:
        return self.match if source_atom.text == target_atom.text else self.mismatch


DEFAULT_COSTS = AlignmentCosts()


@dataclass(frozen=True)
class Op:
    kind: str  # match | sub | delete | insert
    source_index: int | None
    target_index: int | None
    cost: int

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "source_index": self.source_index,
            "target_index": self.target_index,
            "cost": self.cost,
        }


@dataclass
class Alignment:
    ops: list[Op]
    cost: int

    @property
    def links(self) -> list[tuple[int, int]]:
        return [
            (op.source_index, op.target_index)
            for op in self.ops
            if op.source_index is not None and op.target_index is not None
        ]

    def links_for_source(self, source_index: int) -> list[int]:
        return [t for s, t in self.links if s == source_index]

    def diagram(self, source: Sequence[Atom], target: Sequence[Atom]) -> str:
        left: list[str] = []
        bar: list[str] = []
        right: list[str] = []
        for op in self.ops:
            if op.source_index is not None:
                s_text = source[op.source_index].text
            else:
                s_text = "-"
            if op.target_index is not None:
                t_text = target[op.target_index].text
            else:
                t_text = "-"
            width = max(len(s_text), len(t_text), 1)
            left.append(s_text.center(width))
            right.append(t_text.center(width))
            if op.kind == "match":
                mark = "|"
            elif op.kind == "sub":
                mark = "~"
            else:
                mark = " "
            bar.append(mark.center(width))
        return "\n".join(
            [
                "S: " + " ".join(left),
                "   " + " ".join(bar),
                "T: " + " ".join(right),
            ]
        )

    def to_dict(self) -> dict:
        return {"cost": self.cost, "ops": [op.to_dict() for op in self.ops]}


def build_forward(
    source: Sequence[Atom],
    target: Sequence[Atom],
    costs: AlignmentCosts = DEFAULT_COSTS,
) -> list[list[int]]:
    n, m = len(source), len(target)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + costs.delete_source
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] + costs.insert_target
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub_cost = costs.substitution(source[i - 1], target[j - 1])
            dp[i][j] = min(
                dp[i - 1][j - 1] + sub_cost,
                dp[i - 1][j] + costs.delete_source,
                dp[i][j - 1] + costs.insert_target,
            )
    return dp


def build_backward(
    source: Sequence[Atom],
    target: Sequence[Atom],
    costs: AlignmentCosts = DEFAULT_COSTS,
) -> list[list[int]]:
    n, m = len(source), len(target)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n and j == m:
                dp[i][j] = 0
                continue
            best = 10**18
            if i < n:
                best = min(best, costs.delete_source + dp[i + 1][j])
            if j < m:
                best = min(best, costs.insert_target + dp[i][j + 1])
            if i < n and j < m:
                best = min(
                    best,
                    costs.substitution(source[i], target[j]) + dp[i + 1][j + 1],
                )
            dp[i][j] = best
    return dp


def count_forward_paths(
    source: Sequence[Atom],
    target: Sequence[Atom],
    forward: list[list[int]],
    costs: AlignmentCosts = DEFAULT_COSTS,
) -> list[list[int]]:
    n, m = len(source), len(target)
    paths = [[0] * (m + 1) for _ in range(n + 1)]
    paths[0][0] = 1
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            total = 0
            if i > 0 and forward[i][j] == forward[i - 1][j] + costs.delete_source:
                total += paths[i - 1][j]
            if j > 0 and forward[i][j] == forward[i][j - 1] + costs.insert_target:
                total += paths[i][j - 1]
            if i > 0 and j > 0:
                sub = costs.substitution(source[i - 1], target[j - 1])
                if forward[i][j] == forward[i - 1][j - 1] + sub:
                    total += paths[i - 1][j - 1]
            paths[i][j] = total
    return paths


def count_backward_paths(
    source: Sequence[Atom],
    target: Sequence[Atom],
    backward: list[list[int]],
    costs: AlignmentCosts = DEFAULT_COSTS,
) -> list[list[int]]:
    n, m = len(source), len(target)
    paths = [[0] * (m + 1) for _ in range(n + 1)]
    paths[n][m] = 1
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n and j == m:
                continue
            total = 0
            if i < n and backward[i][j] == costs.delete_source + backward[i + 1][j]:
                total += paths[i + 1][j]
            if j < m and backward[i][j] == costs.insert_target + backward[i][j + 1]:
                total += paths[i][j + 1]
            if i < n and j < m:
                sub = costs.substitution(source[i], target[j])
                if backward[i][j] == sub + backward[i + 1][j + 1]:
                    total += paths[i + 1][j + 1]
            paths[i][j] = total
    return paths


def enumerate_optimal_alignments(
    source: Sequence[Atom],
    target: Sequence[Atom],
    costs: AlignmentCosts = DEFAULT_COSTS,
) -> list[Alignment]:
    """Enumerate all minimum-cost Levenshtein alignments.

    Intended for short strings.  The result is a complete list, not a sample.
    """

    forward = build_forward(source, target, costs)
    n, m = len(source), len(target)
    optimum = forward[n][m]
    results: list[Alignment] = []
    rev_ops: list[Op] = []

    def walk(i: int, j: int) -> None:
        if i == 0 and j == 0:
            results.append(Alignment(list(reversed(rev_ops)), optimum))
            return

        # Deterministic predecessor order.
        if i > 0 and forward[i][j] == forward[i - 1][j] + costs.delete_source:
            rev_ops.append(Op("delete", i - 1, None, costs.delete_source))
            walk(i - 1, j)
            rev_ops.pop()

        if j > 0 and forward[i][j] == forward[i][j - 1] + costs.insert_target:
            rev_ops.append(Op("insert", None, j - 1, costs.insert_target))
            walk(i, j - 1)
            rev_ops.pop()

        if i > 0 and j > 0:
            sub = costs.substitution(source[i - 1], target[j - 1])
            if forward[i][j] == forward[i - 1][j - 1] + sub:
                kind = "match" if sub == costs.match else "sub"
                rev_ops.append(Op(kind, i - 1, j - 1, sub))
                walk(i - 1, j - 1)
                rev_ops.pop()

    walk(n, m)
    return results


@dataclass(frozen=True)
class TargetChoice:
    """One optimal way for an output atom to be consumed.

    ``edge_i`` is the source coordinate at which the consuming edge starts.  It
    equals ``source_index`` for a diagonal link and can differ for an insertion
    made at source prefix ``edge_i``.
    """

    target_index: int
    kind: str  # link | insert
    edge_i: int
    source_index: int | None
    through_cost: int
    through_count: int

    def to_dict(self) -> dict:
        return {
            "target_index": self.target_index,
            "kind": self.kind,
            "edge_i": self.edge_i,
            "source_index": self.source_index,
            "through_cost": self.through_cost,
            "through_count": self.through_count,
        }


class Lattice:
    def __init__(
        self,
        source: Sequence[Atom],
        target: Sequence[Atom],
        costs: AlignmentCosts = DEFAULT_COSTS,
    ) -> None:
        self.source = list(source)
        self.target = list(target)
        self.costs = costs
        self.forward = build_forward(source, target, costs)
        self.backward = build_backward(source, target, costs)
        self.prefix_paths = count_forward_paths(source, target, self.forward, costs)
        self.suffix_paths = count_backward_paths(source, target, self.backward, costs)
        self.n = len(source)
        self.m = len(target)
        self.total_cost = self.forward[self.n][self.m]
        self.total_paths = self.prefix_paths[self.n][self.m]
        self._choices: list[list[TargetChoice]] | None = None

    model_name = "ordered_edit"

    def verify_alignment(self, alignment: Alignment) -> dict:
        return verify_alignment(self.source, self.target, alignment, self.costs)

    def diagram(self, alignment: Alignment) -> str:
        return alignment.diagram(self.source, self.target)

    def choices_for_targets(self) -> list[list[TargetChoice]]:
        if self._choices is not None:
            return self._choices
        choices_by_target: list[list[TargetChoice]] = [[] for _ in range(self.m)]
        f, b = self.forward, self.backward
        pp, sp = self.prefix_paths, self.suffix_paths
        c = self.costs

        # Horizontal insertion edge (i, j) -> (i, j+1) consumes target j.
        for j in range(self.m):
            for i in range(self.n + 1):
                through = f[i][j] + c.insert_target + b[i][j + 1]
                if through != self.total_cost:
                    continue
                count = pp[i][j] * sp[i][j + 1]
                if count <= 0:
                    continue
                choices_by_target[j].append(
                    TargetChoice(j, "insert", i, None, through, count)
                )

        # Diagonal edge (i, j) -> (i+1, j+1) consumes target j and source i.
        for j in range(self.m):
            for i in range(self.n):
                sub = c.substitution(self.source[i], self.target[j])
                through = f[i][j] + sub + b[i + 1][j + 1]
                if through != self.total_cost:
                    continue
                count = pp[i][j] * sp[i + 1][j + 1]
                if count <= 0:
                    continue
                choices_by_target[j].append(
                    TargetChoice(j, "link", i, i, through, count)
                )

        # Stable order: links by source index, then insertions by prefix index.
        for j, choices in enumerate(choices_by_target):
            choices.sort(
                key=lambda ch: (
                    0 if ch.kind == "link" else 1,
                    ch.source_index if ch.source_index is not None else 10**9,
                )
            )
        self._choices = choices_by_target
        return choices_by_target

    def _prefix_ops(self, end_i: int, end_j: int) -> list[Op]:
        rev: list[Op] = []
        i, j = end_i, end_j
        f = self.forward
        c = self.costs
        while i > 0 or j > 0:
            if i > 0 and j > 0:
                sub = c.substitution(self.source[i - 1], self.target[j - 1])
                if f[i][j] == f[i - 1][j - 1] + sub:
                    kind = "match" if sub == c.match else "sub"
                    rev.append(Op(kind, i - 1, j - 1, sub))
                    i -= 1
                    j -= 1
                    continue
            if i > 0 and f[i][j] == f[i - 1][j] + c.delete_source:
                rev.append(Op("delete", i - 1, None, c.delete_source))
                i -= 1
                continue
            if j > 0 and f[i][j] == f[i][j - 1] + c.insert_target:
                rev.append(Op("insert", None, j - 1, c.insert_target))
                j -= 1
                continue
            raise RuntimeError("no optimal predecessor; lattice is inconsistent")
        return list(reversed(rev))

    def _suffix_ops(self, start_i: int, start_j: int) -> list[Op]:
        ops: list[Op] = []
        i, j = start_i, start_j
        b = self.backward
        c = self.costs
        while i < self.n or j < self.m:
            if i < self.n and j < self.m:
                sub = c.substitution(self.source[i], self.target[j])
                if b[i][j] == sub + b[i + 1][j + 1]:
                    kind = "match" if sub == c.match else "sub"
                    ops.append(Op(kind, i, j, sub))
                    i += 1
                    j += 1
                    continue
            if i < self.n and b[i][j] == c.delete_source + b[i + 1][j]:
                ops.append(Op("delete", i, None, c.delete_source))
                i += 1
                continue
            if j < self.m and b[i][j] == c.insert_target + b[i][j + 1]:
                ops.append(Op("insert", None, j, c.insert_target))
                j += 1
                continue
            raise RuntimeError("no optimal successor; lattice is inconsistent")
        return ops

    def witness_for_choice(self, choice: TargetChoice) -> Alignment:
        """Reconstruct a minimum alignment containing ``choice``."""

        if choice.kind == "insert":
            j = choice.target_index
            i = choice.edge_i
            ops = self._prefix_ops(i, j)
            ops.append(Op("insert", None, j, self.costs.insert_target))
            ops.extend(self._suffix_ops(i, j + 1))
            return Alignment(ops, self.total_cost)

        assert choice.source_index is not None
        i = choice.source_index
        j = choice.target_index
        sub = self.costs.substitution(self.source[i], self.target[j])
        ops = self._prefix_ops(i, j)
        kind = "match" if sub == self.costs.match else "sub"
        ops.append(Op(kind, i, j, sub))
        ops.extend(self._suffix_ops(i + 1, j + 1))
        return Alignment(ops, self.total_cost)

    def marker_summary(self) -> dict:
        choices = self.choices_for_targets()
        may_links: list[list[int]] = []
        must_links: list[list[int]] = []
        for target_index, target_choices in enumerate(choices):
            link_sources = [
                ch.source_index for ch in target_choices if ch.kind == "link"
            ]
            may_links.extend([[s, target_index] for s in link_sources if s is not None])
            for ch in target_choices:
                if (
                    ch.kind == "link"
                    and ch.source_index is not None
                    and ch.through_count == self.total_paths
                ):
                    must_links.append([ch.source_index, target_index])
        return {
            "source_atoms": self.n,
            "target_atoms": self.m,
            "dp_cells": (self.n + 1) * (self.m + 1),
            "optimal_cost": self.total_cost,
            "optimal_path_count": self.total_paths,
            "may_links": may_links,
            "must_links": must_links,
            "choice_count": sum(len(x) for x in choices),
        }


def verify_alignment(
    source: Sequence[Atom],
    target: Sequence[Atom],
    alignment: Alignment,
    costs: AlignmentCosts = DEFAULT_COSTS,
) -> dict:
    """Independently check consumes, order, cost, and optimality."""

    errors: list[str] = []
    si = ti = 0
    computed_cost = 0
    for pos, op in enumerate(alignment.ops):
        if op.kind == "delete":
            if op.source_index != si or op.target_index is not None:
                errors.append(f"op {pos}: bad delete indices")
            elif si >= len(source):
                errors.append(f"op {pos}: delete past source end")
            else:
                expected = costs.delete_source
                if op.cost != expected:
                    errors.append(f"op {pos}: cost {op.cost} != {expected}")
                computed_cost += op.cost
                si += 1
        elif op.kind == "insert":
            if op.target_index != ti or op.source_index is not None:
                errors.append(f"op {pos}: bad insert indices")
            elif ti >= len(target):
                errors.append(f"op {pos}: insert past target end")
            else:
                expected = costs.insert_target
                if op.cost != expected:
                    errors.append(f"op {pos}: cost {op.cost} != {expected}")
                computed_cost += op.cost
                ti += 1
        elif op.kind in {"match", "sub"}:
            if op.source_index != si or op.target_index != ti:
                errors.append(f"op {pos}: indices ({op.source_index},{op.target_index}) != expected ({si},{ti})")
            elif si >= len(source) or ti >= len(target):
                errors.append(f"op {pos}: diagonal past end")
            else:
                expected = costs.substitution(source[si], target[ti])
                expected_kind = "match" if expected == costs.match else "sub"
                if op.kind != expected_kind:
                    errors.append(f"op {pos}: kind {op.kind} != {expected_kind}")
                if op.cost != expected:
                    errors.append(f"op {pos}: cost {op.cost} != {expected}")
                computed_cost += op.cost
                si += 1
                ti += 1
        else:
            errors.append(f"op {pos}: unknown kind {op.kind}")

    if si != len(source):
        errors.append(f"source not fully consumed: {si}/{len(source)}")
    if ti != len(target):
        errors.append(f"target not fully consumed: {ti}/{len(target)}")
    if computed_cost != alignment.cost:
        errors.append(f"declared cost {alignment.cost} != computed {computed_cost}")

    optimum = build_forward(source, target, costs)[len(source)][len(target)]
    is_minimum = computed_cost == optimum and not errors
    if alignment.cost != optimum and not any("cost" in e for e in errors):
        errors.append(f"alignment cost {alignment.cost} is not optimum {optimum}")

    return {
        "valid": not errors,
        "is_minimum": is_minimum,
        "computed_cost": computed_cost,
        "optimum_cost": optimum,
        "errors": errors,
    }
