"""Captured and sanitized firmware responses."""

from pathlib import Path

import pytest

from custom_components.ifu_wf.api import parse_device, parse_status


@pytest.fixture
def page():
    return (Path(__file__).parent / "fixtures/device.html").read_text()


@pytest.fixture
def status():
    return (Path(__file__).parent / "fixtures/status.xml").read_text()


@pytest.fixture
def device(page):
    return parse_device(page)


@pytest.fixture
def state(device, status):
    return parse_status(status, device)
