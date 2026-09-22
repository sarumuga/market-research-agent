"""
Exposes SearchClient as LangChain tools so agent nodes can call them
directly (or so an LLM using tool-calling/ReAct can invoke them).

Mirrors youcom_tools.py from the original kit: formats raw results
into a single readable text block, which is what an LLM consumes
most reliably (vs. raw JSON/dicts).
"""

from langchain_core.tools import tool

from tools.search_client import get_search_client


def _format_results(results: list[dict]) -> str:
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, start=1):
        lines.append(f"{i}. {r['title']}\n   URL: {r['url']}\n   {r['snippet']}")
    return "\n\n".join(lines)


@tool
def web_search(query: str) -> str:
    """Search the general web for a query. Use this for company info,
    product features, pricing, and market positioning."""
    client = get_search_client()
    results = client.search(query, topic="general", max_results=5)
    return _format_results(results)


@tool
def news_search(query: str) -> str:
    """Search recent news for a query. Use this for launches, funding
    rounds, partnerships, and other recent announcements."""
    client = get_search_client()
    results = client.search(query, topic="news", max_results=5)
    return _format_results(results)
