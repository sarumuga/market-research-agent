"""
Lightweight wrapper around the Tavily Search API.

Mirrors the role of youcom_client.py in the original solution kit:
- authenticates with TAVILY_API_KEY
- makes the search request
- returns a clean, structured list of dicts (title/url/snippet)

Kept as a small class (not free functions) so it's easy to swap in a
different provider (e.g. you.com) later without touching the tools
or graph layers — they only depend on this class's public methods.
"""

import os
from typing import Literal

from tavily import TavilyClient


class SearchClient:
    """Singleton-style wrapper around Tavily. One instance is reused
    across the app so we don't reconnect per call."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("TAVILY_API_KEY")
        if not key:
            raise ValueError(
                "TAVILY_API_KEY not found. Copy .env.example to .env "
                "and add your real Tavily API key."
            )
        self._client = TavilyClient(api_key=key)

    def search(
        self,
        query: str,
        topic: Literal["general", "news"] = "general",
        max_results: int = 5,
    ) -> list[dict]:
        """
        Run a search and return cleaned results.

        topic="general" -> broad web search (features, pricing, positioning)
        topic="news"    -> recent news search (launches, funding, partnerships)
        """
        raw = self._client.search(
            query=query,
            topic=topic,
            max_results=max_results,
            search_depth="basic",
        )

        results = []
        for item in raw.get("results", []):
            results.append(
                {
                    "title": item.get("title", "").strip(),
                    "url": item.get("url", "").strip(),
                    "snippet": item.get("content", "").strip(),
                }
            )
        return results


_client_instance: SearchClient | None = None


def get_search_client() -> SearchClient:
    """Returns a shared SearchClient instance (created on first call)."""
    global _client_instance
    if _client_instance is None:
        _client_instance = SearchClient()
    return _client_instance
