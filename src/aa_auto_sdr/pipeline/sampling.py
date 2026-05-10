"""Sample a list of RSIDs for --batch generation.

Pure functions — no I/O, no API calls, no SDK. Operates on the
user-supplied RSID list directly. Stratification key is the RSID code
prefix (split on first '.', '_', or '-'); no name resolution.

Mirrors cja_auto_sdr/org/analyzer.py::_stratified_sample with cja's
data-view dicts replaced by AA's bare RSID strings.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Literal

SampleStrategy = Literal["random", "stratified"]
_PREFIX_SEPARATORS = (".", "_", "-")


def _prefix_of(rsid: str) -> str:
    """Return the lowercased prefix before the first '.', '_', or '-'.

    Falls back to the full lowercased RSID if no separator is present.
    """
    lowered = rsid.lower()
    earliest = len(lowered)
    for sep in _PREFIX_SEPARATORS:
        idx = lowered.find(sep)
        if idx != -1 and idx < earliest:
            earliest = idx
    return lowered[:earliest]


def sample_rsids(
    rsids: list[str],
    *,
    sample_size: int,
    seed: int | None = None,
    stratified: bool = False,
) -> list[str]:
    """Return a sampled subset of `rsids`.

    Args:
        rsids: User-supplied RSID list. Caller ensures non-empty.
        sample_size: Target subset size. Must be >= 1. If >= len(rsids),
                     returns the full list unchanged (no shuffle).
        seed: Optional RNG seed for reproducibility.
        stratified: True → group by RSID code prefix and sample proportionally.

    Raises:
        ValueError: sample_size < 1.
    """
    if sample_size < 1:
        raise ValueError(f"sample_size must be >= 1, got {sample_size}")
    if sample_size >= len(rsids):
        return list(rsids)

    rng = random.Random(seed)  # noqa: S311 — statistical sampling, not cryptographic
    if not stratified:
        return rng.sample(rsids, sample_size)

    groups: dict[str, list[str]] = defaultdict(list)
    for rsid in rsids:
        groups[_prefix_of(rsid)].append(rsid)

    total = len(rsids)
    sampled: list[str] = []
    for group in groups.values():
        per_group = max(1, int(sample_size * len(group) / total))
        if len(group) <= per_group:
            sampled.extend(group)
        else:
            sampled.extend(rng.sample(group, per_group))

    if len(sampled) > sample_size:
        sampled = rng.sample(sampled, sample_size)
    elif len(sampled) < sample_size:
        remaining = [r for r in rsids if r not in sampled]
        needed = min(sample_size - len(sampled), len(remaining))
        if needed:
            sampled.extend(rng.sample(remaining, needed))

    return sampled
