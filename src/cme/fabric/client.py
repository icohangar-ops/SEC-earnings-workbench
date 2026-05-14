"""Microsoft Fabric Lakehouse REST API client.

Provides read/write access to Delta tables in the Fabric Lakehouse
for the SEC Earnings Workbench. Used by the Fabric notebook pipeline
to persist research sessions, agent outputs, filings, and artifacts.

Configuration (via .env or constructor):
  FABRIC_WORKSPACE_ID — GUID of the Fabric workspace
  FABRIC_LAKEHOUSE_ID  — GUID of the Lakehouse
  FABRIC_AUTH_MODE     — "token" (default) or "notebook"
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FabricConfig:
    workspace_id: str
    lakehouse_id: str
    auth_mode: str = "token"
    base_url: str = "https://api.fabric.microsoft.com/v1"

    @classmethod
    def from_env(cls) -> FabricConfig:
        return cls(
            workspace_id=os.environ.get("FABRIC_WORKSPACE_ID", ""),
            lakehouse_id=os.environ.get("FABRIC_LAKEHOUSE_ID", ""),
            auth_mode=os.environ.get("FABRIC_AUTH_MODE", "token"),
        )


class FabricClient:
    """Read-only Fabric REST API client for Lakehouse metadata.

    Note: Delta table writes should be done via PySpark in Fabric notebooks
    (spark.write.format("delta").saveAsTable()). This client is for metadata
    operations like listing tables, checking workspace status, etc.
    """

    def __init__(self, config: Optional[FabricConfig] = None) -> None:
        self.config = config or FabricConfig.from_env()
        self._token_cache: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.config.workspace_id and self.config.lakehouse_id)

    def _get_token(self) -> str:
        if self._token_cache:
            return self._token_cache
        if self.config.auth_mode == "notebook":
            from notebookutils import credentials
            self._token_cache = credentials.getToken("https://api.fabric.microsoft.com")
            return self._token_cache

        result = subprocess.run(
            ["az", "account", "get-access-token",
             "--resource", "https://api.fabric.microsoft.com",
             "--query", "accessToken", "--output", "tsv"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to get Fabric token: {result.stderr}")
        self._token_cache = result.stdout.strip()
        return self._token_cache

    def _request(self, path: str) -> Any:
        token = self._get_token()
        url = f"{self.config.base_url}{path}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Fabric API {e.code} for {url}: {body}") from e

    def get_workspace(self) -> Dict[str, Any]:
        return self._request(f"/workspaces/{self.config.workspace_id}")

    def get_lakehouse(self) -> Dict[str, Any]:
        return self._request(
            f"/workspaces/{self.config.workspace_id}"
            f"/lakehouses/{self.config.lakehouse_id}"
        )

    def list_tables(self) -> List[Dict[str, Any]]:
        return self._request(
            f"/workspaces/{self.config.workspace_id}"
            f"/lakehouses/{self.config.lakehouse_id}/tables"
        ).get("value", [])

    def get_table(self, table_name: str) -> Dict[str, Any]:
        tables = self.list_tables()
        for t in tables:
            if t.get("name", "").lower() == table_name.lower():
                return t
        raise KeyError(f"Table '{table_name}' not found in Lakehouse")

    def health_check(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"configured": self.is_configured}
        if not self.is_configured:
            return result
        try:
            ws = self.get_workspace()
            result["workspace"] = ws.get("displayName", "unknown")
            result["workspace_id"] = self.config.workspace_id
        except Exception as e:
            result["workspace_error"] = str(e)
        try:
            lh = self.get_lakehouse()
            result["lakehouse"] = lh.get("displayName", "unknown")
            result["lakehouse_id"] = self.config.lakehouse_id
        except Exception as e:
            result["lakehouse_error"] = str(e)
        return result
