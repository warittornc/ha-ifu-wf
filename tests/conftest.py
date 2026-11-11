"""Captured and sanitized firmware responses."""

from pathlib import Path

import pytest

from custom_components.ifu_wf.api import parse_state


@pytest.fixture
def page():
    return (Path(__file__).parent / "fixtures/device.html").read_text()


@pytest.fixture
def status():
    return (Path(__file__).parent / "fixtures/status.xml").read_text()


@pytest.fixture
def state(page, status):
    return parse_state(page, status)
