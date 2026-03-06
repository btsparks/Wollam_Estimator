"""
Tests for HCSS Client Module

Basic structural tests — no live API calls. Validates that the
client modules instantiate correctly and handle missing credentials
gracefully.
"""

import pytest

from app.hcss.auth import HCSSAuth
from app.hcss.client import HCSSClient
from app.hcss.heavyjob import HeavyJobAPI
from app.hcss.heavybid import HeavyBidAPI
from app.hcss.models import HBEstimate
from app.hcss.sync import HCSSSyncOrchestrator


class TestHCSSAuth:
    """Test OAuth authentication manager."""

    def test_auth_not_configured_empty_credentials(self):
        """Empty credentials should report is_configured = False."""
        auth = HCSSAuth(client_id="", client_secret="")
        assert auth.is_configured is False

    def test_auth_not_configured_none_credentials(self, monkeypatch):
        """None credentials (with no env vars) should report is_configured = False."""
        monkeypatch.delenv("HCSS_CLIENT_ID", raising=False)
        monkeypatch.delenv("HCSS_CLIENT_SECRET", raising=False)
        auth = HCSSAuth(client_id=None, client_secret=None)
        assert auth.is_configured is False

    def test_auth_configured_with_credentials(self):
        """Valid credentials should report is_configured = True."""
        auth = HCSSAuth(client_id="test-id", client_secret="test-secret")
        assert auth.is_configured is True

    @pytest.mark.asyncio
    async def test_auth_get_token_fails_without_credentials(self):
        """Calling get_token without credentials raises RuntimeError."""
        auth = HCSSAuth(client_id="", client_secret="")
        with pytest.raises(RuntimeError, match="HCSS API credentials not configured"):
            await auth.get_token()


class TestHeavyJobAPI:
    """Test HeavyJob API wrapper instantiation."""

    def test_heavyjob_api_instantiation(self):
        """HeavyJobAPI instantiates without errors."""
        auth = HCSSAuth(client_id="test", client_secret="test")
        client = HCSSClient(auth, base_url="https://api.hcss.com/heavyjob")
        hj = HeavyJobAPI(client, business_unit_id="test-bu-id")
        assert hj is not None


class TestHeavyBidAPI:
    """Test HeavyBid API wrapper instantiation."""

    def test_heavybid_api_instantiation(self):
        """HeavyBidAPI instantiates without errors."""
        auth = HCSSAuth(client_id="test", client_secret="test")
        client = HCSSClient(auth, base_url="https://api.hcss.com/heavybid")
        hb = HeavyBidAPI(client, business_unit_id="test-bu-id")
        assert hb is not None


class TestSyncOrchestrator:
    """Test sync orchestrator (stub methods)."""

    def test_sync_instantiation(self):
        """Sync orchestrator instantiates without errors."""
        sync = HCSSSyncOrchestrator()
        assert sync is not None

    def test_match_estimate_to_job_found(self):
        """match_estimate_to_job finds estimate when job number is in name."""
        sync = HCSSSyncOrchestrator()
        estimates = [
            HBEstimate(name="8553 RTK SPD Pump Station", id="est-1"),
            HBEstimate(name="8576 RTKC 5600 Pump Station", id="est-2"),
            HBEstimate(name="Other Project", id="est-3"),
        ]
        result = sync.match_estimate_to_job("8553", estimates)
        assert result is not None
        assert result.id == "est-1"

    def test_match_estimate_to_job_not_found(self):
        """match_estimate_to_job returns None when no match."""
        sync = HCSSSyncOrchestrator()
        estimates = [
            HBEstimate(name="Other Project", id="est-1"),
        ]
        result = sync.match_estimate_to_job("8553", estimates)
        assert result is None

    def test_match_estimate_to_job_empty_list(self):
        """match_estimate_to_job handles empty estimate list."""
        sync = HCSSSyncOrchestrator()
        result = sync.match_estimate_to_job("8553", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_sync_all_raises_without_sources(self):
        """sync_all_closed_jobs raises RuntimeError without data sources."""
        sync = HCSSSyncOrchestrator()
        with pytest.raises(RuntimeError, match="No data sources configured"):
            await sync.sync_all_closed_jobs()
