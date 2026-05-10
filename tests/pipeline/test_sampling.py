"""Pure sampling logic — pipeline/sampling.py."""

from __future__ import annotations

import pytest

from aa_auto_sdr.pipeline.sampling import _prefix_of, sample_rsids


class TestPrefixOf:
    def test_dot_separator(self) -> None:
        assert _prefix_of("acme.prod.us") == "acme"

    def test_underscore_separator(self) -> None:
        assert _prefix_of("acme_prod_us") == "acme"

    def test_dash_separator(self) -> None:
        assert _prefix_of("acme-prod-us") == "acme"

    def test_first_separator_wins(self) -> None:
        # Mixed separators: split on whichever appears first.
        assert _prefix_of("acme.prod_us") == "acme"
        assert _prefix_of("acme_prod.us") == "acme"

    def test_lowercased(self) -> None:
        assert _prefix_of("ACME.PROD.US") == "acme"
        assert _prefix_of("Acme_Prod") == "acme"

    def test_no_separator_returns_full_lowercased(self) -> None:
        assert _prefix_of("MYRSID") == "myrsid"
        assert _prefix_of("rsid42") == "rsid42"

    def test_empty_string(self) -> None:
        assert _prefix_of("") == ""


class TestSampleRsidsValidation:
    def test_zero_size_raises(self) -> None:
        with pytest.raises(ValueError, match=r"sample_size must be >= 1"):
            sample_rsids(["a", "b"], sample_size=0)

    def test_negative_size_raises(self) -> None:
        with pytest.raises(ValueError, match=r"sample_size must be >= 1"):
            sample_rsids(["a", "b"], sample_size=-3)


class TestSampleRsidsRandom:
    def test_n_eq_total_returns_input_unchanged(self) -> None:
        # No shuffle: order preserved when sample_size >= len(rsids).
        rsids = ["a", "b", "c"]
        assert sample_rsids(rsids, sample_size=3) == ["a", "b", "c"]

    def test_n_gt_total_returns_input_unchanged(self) -> None:
        rsids = ["a", "b"]
        assert sample_rsids(rsids, sample_size=99) == ["a", "b"]

    def test_seed_determinism(self) -> None:
        rsids = [f"rs{i}" for i in range(20)]
        a = sample_rsids(rsids, sample_size=5, seed=42)
        b = sample_rsids(rsids, sample_size=5, seed=42)
        assert a == b
        assert len(a) == 5
        assert set(a).issubset(set(rsids))

    def test_different_seeds_diverge(self) -> None:
        # Probabilistic; 20-choose-5 with two distinct seeds almost never collide.
        rsids = [f"rs{i}" for i in range(20)]
        a = sample_rsids(rsids, sample_size=5, seed=1)
        b = sample_rsids(rsids, sample_size=5, seed=2)
        assert a != b


class TestSampleRsidsStratified:
    def test_proportional_allocation(self) -> None:
        # 8 prod_*, 4 staging_*, 2 dev_*; sample 7 with stratification.
        rsids = [f"prod_{i}" for i in range(8)] + [f"staging_{i}" for i in range(4)] + [f"dev_{i}" for i in range(2)]
        result = sample_rsids(rsids, sample_size=7, seed=0, stratified=True)
        assert len(result) == 7
        prefixes = [_prefix_of(r) for r in result]
        # All three groups represented (max(1, ...) floor + topup).
        assert "prod" in prefixes
        assert "staging" in prefixes
        assert "dev" in prefixes

    def test_single_group_falls_back_to_random(self) -> None:
        rsids = [f"acme.{i}" for i in range(10)]
        result = sample_rsids(rsids, sample_size=3, seed=0, stratified=True)
        assert len(result) == 3
        assert set(result).issubset(set(rsids))

    def test_no_separator_each_rsid_own_group(self) -> None:
        # Every RSID lacks a separator → each is its own group → behaves like random.
        rsids = ["aaa", "bbb", "ccc", "ddd"]
        result = sample_rsids(rsids, sample_size=2, seed=0, stratified=True)
        assert len(result) == 2
        assert set(result).issubset(set(rsids))

    def test_stratified_seed_determinism(self) -> None:
        rsids = [f"prod_{i}" for i in range(8)] + [f"staging_{i}" for i in range(4)] + [f"dev_{i}" for i in range(2)]
        a = sample_rsids(rsids, sample_size=6, seed=42, stratified=True)
        b = sample_rsids(rsids, sample_size=6, seed=42, stratified=True)
        assert a == b

    def test_stratified_n_eq_total_returns_unchanged(self) -> None:
        rsids = ["prod_a", "prod_b", "dev_c"]
        assert sample_rsids(rsids, sample_size=3, seed=0, stratified=True) == rsids

    def test_stratified_trim_when_groups_oversample(self) -> None:
        # 4 single-item groups, sample_size=3.
        # Each group allocated max(1, int(3*1/4)) = max(1, 0) = 1 → 4 collected → trim to 3.
        rsids = ["a.1", "b.1", "c.1", "d.1"]
        result = sample_rsids(rsids, sample_size=3, seed=0, stratified=True)
        assert len(result) == 3

    def test_stratified_topup_when_allocation_underfills(self) -> None:
        # 3 equal groups × 5 each = 15 total. sample_size=4 → each group allocated
        # max(1, int(4*5/15)) = max(1, 1) = 1 → 3 collected → topup adds 1 → 4.
        rsids = [f"a_{i}" for i in range(5)] + [f"b_{i}" for i in range(5)] + [f"c_{i}" for i in range(5)]
        result = sample_rsids(rsids, sample_size=4, seed=0, stratified=True)
        assert len(result) == 4
        assert set(result).issubset(set(rsids))
