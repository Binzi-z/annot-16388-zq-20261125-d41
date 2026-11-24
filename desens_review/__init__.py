"""Offline cross-version desensitization review (Python 3.12 standard library).

The package implements an explicit, auditable alignment model.  The short-string
entry points can enumerate *every* minimum-cost alignment; the lattice entry
points compute must/may alignment markers without enumerating an exponential
number of paths.
"""

from .model import (
    Atom,
    ClassifiedSpan,
    Downgrade,
    Level,
    ReviewCase,
    word_atoms,
    character_atoms,
)
from .align import (
    Alignment,
    AlignmentCosts,
    Lattice,
    Op,
    enumerate_optimal_alignments,
    verify_alignment,
)
from .review import review_case, ReviewResult
from .transport import (
    TransportLattice,
    enumerate_transport_alignments,
    verify_transport_alignment,
)

__all__ = [
    "Atom",
    "ClassifiedSpan",
    "Downgrade",
    "Level",
    "ReviewCase",
    "word_atoms",
    "character_atoms",
    "Alignment",
    "AlignmentCosts",
    "Lattice",
    "Op",
    "enumerate_optimal_alignments",
    "verify_alignment",
    "TransportLattice",
    "enumerate_transport_alignments",
    "verify_transport_alignment",
    "review_case",
    "ReviewResult",
]
