#!/usr/bin/env python3
"""Windows-friendly wrapper: ``py -3.12 review.py <command>``."""

from desens_review.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
