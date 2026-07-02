"""Permanent pandas column-slice KeyError must not be retried."""

from __future__ import annotations

import pytest

from aa_auto_sdr.api import resilience
from aa_auto_sdr.core.exceptions import ApiError, TransientApiError


def test_not_in_index_keyerror_is_permanent():
    def boom():
        raise KeyError("['dataGroup'] not in index")

    with pytest.raises(ApiError) as ei:
        resilience.classify_transient_sdk_call(boom, component_type="metric")
    assert not isinstance(ei.value, TransientApiError)
    assert not resilience.is_retryable(ei.value)


def test_other_keyerror_still_transient():
    def boom():
        raise KeyError("content")

    with pytest.raises(TransientApiError) as ei:
        resilience.classify_transient_sdk_call(boom)
    assert resilience.is_retryable(ei.value)


def test_value_error_still_transient():
    def boom():
        raise ValueError("Expected object or value")

    with pytest.raises(TransientApiError) as ei:
        resilience.classify_transient_sdk_call(boom, component_type="segment")
    assert resilience.is_retryable(ei.value)
    assert "segment transient SDK failure" in str(ei.value)
