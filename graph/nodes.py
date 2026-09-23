"""
The three worker nodes of the market research graph.

    discovery_node  -> finds the top-3 competitors, fills competitor_queue
    researcher_node -> web + news search for the competitor at the head
                       of the queue, stores the text in raw_research
    analyst_node    -> turns that raw text into a CompetitorReport via
                       Groq structured output, then pops the queue

The queue is only popped by the Analyst, so the Researcher and Analyst
always agree on which competitor is "current" (competitor_queue[0]).
The router (graph/router.py) decides whether to loop back or finish.

Every node returns a partial state dict and appends at least one line
to status_log so the Streamlit UI can show live progress.
"""

import os
from functools import lru_cache

from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from graph.state import AgentState, CompetitorReport
from tools.search_tools import news_search, web_search

# Llama 3.3 70B (the kit's model) has been retired on Groq; gpt-oss-120b is
# the strongest general model currently available there. Override via .env.
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"
MAX_COMPETITORS = 3
NOT_FOUND = "Data not found"


class CompetitorList(BaseModel):
    """Structured-output target for the Discovery node."""

    competitors: list[str] = Field(
        description="Names of the top direct competitors, most relevant first."
    )


@lru_cache(maxsize=1)
def _get_llm() -> ChatGroq:
    """Shared Groq client, created on first use (not at import time) so
    importing this module doesn't require GROQ_API_KEY to be set."""
    return ChatGroq(model=os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL), temperature=0)


DISCOVERY_SYSTEM_PROMPT = """You identify direct competitors of a company \
using the search results provided.

Rules:
- Return exactly {n} competitor company or product names, most direct first.
- Only use names that appear in the search results. Do not invent companies.
- Do not include the target company itself or its own sub-products.
- Return names only, no descriptions."""

ANALYST_SYSTEM_PROMPT = f"""You are a competitive market analyst. Build a \
structured report on one competitor using ONLY the research provided.

Guardrails:
- Do not invent competitor details that are not present in the research.
- Do not assume features or pricing. If pricing is not stated, say "{NOT_FOUND}".
- Use "{NOT_FOUND}" for any field the research does not support.
- core_features: 3-5 short items taken from the research; if none are \
found, return ["{NOT_FOUND}"].
- Be concise and factual. No marketing language or superlatives."""


def discovery_node(state: AgentState) -> dict:
    company = state["company_name"]
    log = [f"Discovery: Scanning market for '{company}' competitors..."]

    results = web_search.invoke({"query": f"top competitors and alternatives to {company}"})

    llm = _get_llm().with_structured_output(CompetitorList)
    response = llm.invoke(
        [
            ("system", DISCOVERY_SYSTEM_PROMPT.format(n=MAX_COMPETITORS)),
            ("human", f"Target company: {company}\n\nSearch results:\n{results}"),
        ]
    )

    # Dedupe (case-insensitive), drop the target company, cap at 3.
    seen = {company.strip().lower()}
    competitors = []
    for name in response.competitors:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            competitors.append(name.strip())
    competitors = competitors[:MAX_COMPETITORS]

    if competitors:
        log.append(f"Discovery: Found competitors: {', '.join(competitors)}")
    else:
        log.append(f"Discovery: No competitors found for '{company}'.")

    return {
        "competitor_queue": competitors,
        "raw_research": {},
        "status_log": log,
    }


def researcher_node(state: AgentState) -> dict:
    # Discovery can come back empty; nothing to research in that case.
    if not state["competitor_queue"]:
        return {"status_log": ["Researcher: Queue empty, nothing to research."]}

    competitor = state["competitor_queue"][0]
    log = [f"Researcher: Searching web and news for '{competitor}'..."]

    web = web_search.invoke(
        {"query": f"{competitor} pricing features target market"}
    )
    news = news_search.invoke(
        {"query": f"{competitor} launch funding partnership"}
    )

    # raw_research has no reducer, so return the full merged dict.
    raw_research = {
        **state.get("raw_research", {}),
        competitor: f"WEB RESULTS:\n{web}\n\nNEWS RESULTS:\n{news}",
    }
    log.append(f"Researcher: Collected sources for '{competitor}'.")

    return {"raw_research": raw_research, "status_log": log}


def analyst_node(state: AgentState) -> dict:
    queue = state["competitor_queue"]
    if not queue:
        return {"status_log": ["Analyst: Queue empty, nothing to analyze."]}

    competitor = queue[0]
    research = state.get("raw_research", {}).get(competitor, "No results found.")
    log = [f"Analyst: Building report for '{competitor}'..."]

    llm = _get_llm().with_structured_output(CompetitorReport)
    try:
        report = llm.invoke(
            [
                ("system", ANALYST_SYSTEM_PROMPT),
                (
                    "human",
                    f"Competitor: {competitor}\n"
                    f"(Competing with: {state['company_name']})\n\n"
                    f"Research:\n{research}",
                ),
            ]
        )
        report_dict = report.model_dump()
        # Keep the name consistent with the queue, not whatever the LLM echoed.
        report_dict["competitor_name"] = competitor
        log.append(f"Analyst: Report complete for '{competitor}'.")
    except Exception as exc:
        # One bad LLM response shouldn't kill the whole run; emit a
        # placeholder report and keep looping through the queue.
        report_dict = CompetitorReport(
            competitor_name=competitor,
            pricing_model=NOT_FOUND,
            core_features=[NOT_FOUND],
            market_positioning=NOT_FOUND,
            recent_news=NOT_FOUND,
        ).model_dump()
        log.append(f"Analyst: Failed to analyze '{competitor}' ({exc}).")

    return {
        "competitor_queue": queue[1:],
        "final_reports": [report_dict],
        "status_log": log,
    }
