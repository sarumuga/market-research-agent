# Build Log / Prompt Log

Running log of how this project was built with AI pair-programming (Claude),
kept for the course's "prompts you used during vibe coding" deliverable.

## Session 1 — Planning

- Provided the "Market Research Agent — Solution Kit (you.com)" PDF and asked
  for a step-by-step build plan for a course-work multi-agent app.
- Decision: keep the kit's 3-node + queue-router LangGraph design
  (Discovery -> Researcher -> Analyst -> Router), but swap you.com for
  **Tavily** (free tier, simpler API, native web/news topic split) to avoid
  a paid/harder-to-access dependency. Kept Groq for the LLM since a paid key
  was already available.
- Decision: keep the search client behind a small class interface
  (`SearchClient`) so the provider could be swapped without touching the
  graph or tool layer.

## Session 2 — Scaffolding

- Created repo structure: `graph/`, `tools/`, `prompts/`, `tests/`, `docs/`.
- Wrote `requirements.txt`, `.env.example`, `.gitignore`.
- Wrote `tools/search_client.py` (Tavily wrapper) and `tools/search_tools.py`
  (LangChain `@tool` wrappers: `web_search`, `news_search`), mirroring the
  kit's `youcom_client.py` / `youcom_tools.py` split.

## Next up

- `graph/state.py`: AgentState + CompetitorReport schema
- `graph/nodes.py`, `graph/router.py`, `graph/build_graph.py`
- `app.py`: Streamlit UI
- End-to-end test with a real company name
