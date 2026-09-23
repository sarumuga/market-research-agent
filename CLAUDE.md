# Project Context for Claude Code

This file is auto-read by Claude Code at the start of a session in this
repo. It captures decisions made so far so you don't have to re-explain
them.

## What this is

A course-work multi-agent competitive market research app. Given a company
name, it discovers top-3 competitors, researches each via web+news search,
and produces structured competitor reports, displayed in a Streamlit UI.

Adapted from a reference "Solution Kit" that used you.com + Groq; this
build uses **Tavily** in place of you.com (free tier, simpler API, native
web/news topic split via `topic="general"` vs `topic="news"`).

## Architecture (LangGraph)

```
Streamlit UI -> Discovery Node -> Researcher Node (loops per competitor)
                                        |  ^
                                        v  |
                                   Analyst Node -> Queue Router
                                        |
                          (loop back to Researcher until queue empty)
                                        |
                                       END -> Streamlit displays cards
```

Same 3-node + queue-router pattern as the reference kit. Human review is
the final step — the graph intentionally stops after generating reports;
no DB writes, emails, or automated actions.

## Stack

- LangGraph (orchestration) + LangChain (LLM/tool glue)
- Groq via `ChatGroq(...).with_structured_output(CompetitorReport)`. Model is
  `openai/gpt-oss-120b` by default (override with `GROQ_MODEL` in `.env`) —
  Llama 3.3 70B from the reference kit has been retired on Groq.
- Tavily (`tavily-python`) for search
- Streamlit for the UI
- Pydantic for the `CompetitorReport` schema

## Files completed so far

- `tools/search_client.py` — `SearchClient` class wrapping Tavily; kept as
  a class (not free functions) so the provider is swappable later.
- `tools/search_tools.py` — `web_search` / `news_search`, LangChain
  `@tool`-decorated wrappers around `SearchClient`, formatted as readable
  text blocks (LLMs parse text more reliably than raw JSON).
- `graph/state.py` — `AgentState` (TypedDict) and `CompetitorReport`
  (Pydantic model). Key detail: `final_reports` and `status_log` use
  `Annotated[list, operator.add]` as a LangGraph reducer, so each loop
  iteration *appends* rather than overwrites — required because the
  Researcher/Analyst pair runs once per competitor in a loop.
- `graph/nodes.py` — `discovery_node`, `researcher_node`, `analyst_node`.
  Discovery does one `web_search` and uses Groq structured output
  (`CompetitorList`) to pick 3 competitors (deduped, target company
  excluded). Researcher runs `web_search` + `news_search` on
  `competitor_queue[0]` and stores the text in `raw_research` (returns the
  full merged dict, since that key has no reducer). Analyst builds a
  `CompetitorReport` from that text with the guardrail prompt, then pops
  the queue — **only the Analyst pops**, so both nodes always agree on the
  current competitor. On LLM failure the Analyst emits a "Data not found"
  placeholder report instead of crashing. LLM is created lazily
  (`_get_llm`, temperature 0, model from `GROQ_MODEL` env var).
- `graph/router.py` — `queue_router`: returns `"researcher"` if
  `competitor_queue` is non-empty, else `END`. Used after both Discovery
  (so an empty discovery result ends the run) and Analyst (the loop).
- `graph/build_graph.py` — `build_graph()` compiles the `StateGraph`
  (START -> discovery -> router -> researcher -> analyst -> router);
  `initial_state(company)` builds a fully-populated starting state.
- `app.py` — Streamlit UI. Checks API keys up front, streams the graph with
  `stream_mode="updates"` so `status_log` lines appear live inside an
  `st.status` box, then renders one expander card per report. Results are
  kept in `st.session_state` so they survive reruns.

## Not yet built (next steps, in order)

1. More end-to-end testing with real company names; tune the Discovery
   query/prompt if competitor picks look off (e.g. a "Notion" run returned
   Airtable, Craft Agents, Scribe — Coda/Confluence would be expected)
2. `docs/architecture.md` write-up (for course submission doc)

## Conventions to keep

- Prompt guardrails for the Analyst node (from the reference kit): do not
  invent competitor details not present in search results; do not assume
  features/pricing; use "Data not found" for missing fields; concise, no
  marketing language.
- Every node should append a human-readable line to `status_log` (e.g.
  "Discovery: Scanning market for 'Figma' competitors...") so the
  Streamlit UI can show live progress, matching the reference kit's UX.
- Keep `docs/prompts_log.md` updated with build decisions as you go — it
  feeds the course's "prompts/iterations" documentation deliverable.
