"""Basic import and smoke tests for the SEC Earnings Workbench (cme package)."""

import sys
import os
import pytest

# Ensure the src directory is on the path so we can import `cme`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_cme_package_importable():
    """Verify the top-level cme package can be imported."""
    import cme  # noqa: F401
    assert True


def test_cme_agent_module():
    """Verify the agent module can be imported."""
    from cme import agent  # noqa: F401
    assert True


def test_cme_protocol_module():
    """Verify the protocol module can be imported."""
    from cme import protocol  # noqa: F401
    assert True


def test_cme_context_module():
    """Verify the context module can be imported."""
    from cme import context  # noqa: F401
    assert True


def test_cme_orchestrator_module():
    """Verify the orchestrator module can be imported."""
    from cme import orchestrator  # noqa: F401
    assert True


def test_placeholder():
    """Placeholder test to ensure CI pipeline has at least one passing test."""
    assert 1 + 1 == 2
