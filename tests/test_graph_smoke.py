"""
Offline smoke test for the full LangGraph pipeline.

Search tools and the Groq LLM are replaced with fakes, so this runs in
about a second with no API keys and no network. It checks the wiring:
Discovery fills the queue, the Researcher/Analyst loop runs once per
competitor, and the run ends with 3 valid CompetitorReport entries.

Run with:  python -m pytest
"""

from unittest.mock import MagicMock

import pytest

import graph.nodes as nodes
from graph.build_graph import build_graph, initial_state
from graph.state import CompetitorReport

COMPETITORS = ["Sketch", "Adobe XD", "Canva"]


def _fake_search():
    tool = MagicMock()
    tool.invoke.return_value = "1. Example\n   URL: https://example.com\n   snippet"
    return tool


def _fake_llm():
    """Mimics ChatGroq(...).with_structured_output(schema).invoke(...)."""

    def with_structured_output(schema):
        runnable = MagicMock()
        if schema is nodes.CompetitorList:
            runnable.invoke.return_value = nodes.CompetitorList(
                category="Collaborative design tools",
                competitors=COMPETITORS,
            )
        else:
            runnable.invoke.return_value = CompetitorReport(
                competitor_name="placeholder",
                pricing_model="Data not found",
                core_features=["Feature A", "Feature B", "Feature C"],
                market_positioning="Design teams",
                recent_news="Data not found",
            )
        return runnable

    llm = MagicMock()
    llm.with_structured_output.side_effect = with_structured_output
    return llm


@pytest.fixture
def fakes(monkeypatch):
    web, news = _fake_search(), _fake_search()
    monkeypatch.setattr(nodes, "web_search", web)
    monkeypatch.setattr(nodes, "news_search", news)
    monkeypatch.setattr(nodes, "_get_llm", _fake_llm)
    return web, news


def test_graph_produces_three_competitor_reports(fakes):
    web, news = fakes

    final = build_graph().invoke(initial_state("Figma"))

    reports = final["final_reports"]
    assert len(reports) == 3
    for report in reports:
        CompetitorReport.model_validate(report)
    assert [r["competitor_name"] for r in reports] == COMPETITORS

    assert final["competitor_queue"] == []
    # Discovery web searches + 1 web search per competitor; 1 news search each.
    assert web.invoke.call_count == len(nodes.DISCOVERY_QUERIES) + len(COMPETITORS)
    assert news.invoke.call_count == len(COMPETITORS)
    assert any(line.startswith("Discovery:") for line in final["status_log"])
