"""
Shared state definitions for the market research LangGraph pipeline.

AgentState flows through every node (Discovery -> Researcher -> Analyst ->
Router). Each node reads what it needs and returns a partial dict that
LangGraph merges back into the state.

CompetitorReport is the structured-output target for the Analyst node —
matches the "Data Model" section of the original solution kit.
"""

import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class CompetitorReport(BaseModel):
    """Structured findings for a single competitor. Populated by the
    Analyst node via LLM structured output."""

    competitor_name: str = Field(description="Name of the competitor")
    pricing_model: str = Field(
        description="How they monetize; specific prices if found. "
        "'Data not found' if not present in the source material."
    )
    core_features: list[str] = Field(
        description="3-5 main product features, as found in the data."
    )
    market_positioning: str = Field(
        description="Market segment, target users, stated advantages."
    )
    recent_news: str = Field(
        description="Recent launches, funding, or partnerships. "
        "'Data not found' if none present."
    )


class AgentState(TypedDict):
    """
    The graph's shared state.

    company_name: the user's input company (via Streamlit)
    competitor_queue: competitors still needing research + analysis;
        the Researcher/Analyst loop pops from this until it's empty
    raw_research: accumulated raw search text per competitor, keyed by
        competitor name, e.g. {"Adobe XD": "web: ...\\n\\nnews: ..."}
    final_reports: completed CompetitorReport dicts, appended to as
        each competitor finishes the Researcher -> Analyst path
    status_log: human-readable progress messages, appended to by every
        node, surfaced live in the Streamlit UI (mirrors the kit's
        "Discovery: Scanning market for 'Figma' competitors..." style)
    """

    company_name: str
    competitor_queue: list[str]
    raw_research: dict[str, str]
    final_reports: Annotated[list[dict], operator.add]
    status_log: Annotated[list[str], operator.add]
