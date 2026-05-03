"""Azure AI Foundry integration for the SEC Earnings Workbench.

Provides a thin wrapper around the OpenAI-compatible Azure AI Foundry API,
used to power the three research agents (Fundamentals, Diligence, Markets)
and the CHP foundation adjudicator.

Supported deployments:
  - Kimi-K2.6 (Moonshot, via Azure AI Foundry)
  - GPT-4o (OpenAI, via Azure AI Foundry)

Configuration (via .env or constructor):
  AZURE_AI_ENDPOINT — e.g. "https://<resource>.services.ai.azure.com/openai/v1"
  AZURE_AI_KEY       — API key for the Azure AI Foundry resource
  AZURE_AI_DEPLOYMENT — deployment name (e.g. "Kimi-K2.6", "gpt-4o")
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AIMessage:
    role: str
    content: str


@dataclass
class AIResponse:
    content: str
    model: str
    usage: Dict[str, int] = field(default_factory=dict)
    finish_reason: str = ""


class AIFoundryClient:
    """Thin wrapper around Azure AI Foundry (OpenAI-compatible) API.

    Usage::

        client = AIFoundryClient()  # reads from env
        response = client.chat(
            system="You are a financial analyst.",
            user="Analyze AAPL.",
            temperature=0.3,
        )
        print(response.content)
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        deployment: Optional[str] = None,
        api_version: str = "2024-06-01",
    ) -> None:
        self.endpoint = endpoint or os.environ.get(
            "AZURE_AI_ENDPOINT", ""
        )
        self.api_key = api_key or os.environ.get("AZURE_AI_KEY", "")
        self.deployment = deployment or os.environ.get(
            "AZURE_AI_DEPLOYMENT", "Kimi-K2.6"
        )
        self.api_version = api_version
        self._client = None

    @property
    def is_live(self) -> bool:
        return bool(self.endpoint and self.api_key)

    def _get_client(self):
        """Lazy-load the OpenAI client to avoid import errors when offline."""
        if self._client is not None:
            return self._client
        try:
            from openai import AzureOpenAI
            self._client = AzureOpenAI(
                azure_endpoint=self.endpoint,
                api_key=self.api_key,
                api_version=self.api_version,
            )
        except ImportError:
            raise RuntimeError(
                "openai package required for AI Foundry integration. "
                "Install with: pip install openai"
            )
        return self._client

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4000,
        messages: Optional[List[AIMessage]] = None,
    ) -> AIResponse:
        """Send a chat completion request to Azure AI Foundry.

        Args:
            system: System prompt for the AI.
            user: User prompt for the AI.
            temperature: Sampling temperature (0-1).
            max_tokens: Maximum tokens in the response.
            messages: Optional additional conversation messages.

        Returns:
            AIResponse with content, model name, and usage stats.
        """
        if not self.is_live:
            raise RuntimeError(
                "AI Foundry client not configured. "
                "Set AZURE_AI_ENDPOINT and AZURE_AI_KEY."
            )

        client = self._get_client()
        msg_list: List[Dict[str, str]] = [
            {"role": "system", "content": system},
        ]
        if messages:
            for m in messages:
                msg_list.append({"role": m.role, "content": m.content})
        msg_list.append({"role": "user", "content": user})

        response = client.chat.completions.create(
            model=self.deployment,
            messages=msg_list,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        usage = {}
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens or 0,
                "completion_tokens": response.usage.completion_tokens or 0,
                "total_tokens": response.usage.total_tokens or 0,
            }

        return AIResponse(
            content=choice.message.content or "",
            model=response.model or self.deployment,
            usage=usage,
            finish_reason=choice.finish_reason or "",
        )

    def chat_stream(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ):
        """Stream a chat completion response.

        Yields content chunks as they arrive.
        """
        if not self.is_live:
            raise RuntimeError(
                "AI Foundry client not configured. "
                "Set AZURE_AI_ENDPOINT and AZURE_AI_KEY."
            )

        client = self._get_client()
        response = client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
