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

## Session 3 — State schema

- Wrote `graph/state.py`: `AgentState` (TypedDict) and `CompetitorReport`
  (Pydantic). `final_reports` and `status_log` use
  `Annotated[list, operator.add]` so each loop iteration appends.
- Added `CLAUDE.md` as a project brief so each new Claude Code session
  starts with the decisions made so far.

## Session 4 — Graph nodes

- Prompt: "Implement graph/nodes.py with three functions: discovery_node,
  researcher_node, and analyst_node, operating on AgentState. Use the
  web_search and news_search tools. Use ChatGroq with
  .with_structured_output(CompetitorReport) for the analyst node. Follow the
  guardrails and status_log conventions described in CLAUDE.md."
- Decision: Discovery also uses structured output (a small `CompetitorList`
  model) instead of parsing free text, so the queue is always a clean list
  of names. Post-processing dedupes, drops the target company, caps at 3.
- Decision: only the Analyst pops `competitor_queue`; the Researcher just
  reads `competitor_queue[0]`. Keeps the "current competitor" unambiguous
  across the two nodes, and the router only has to check for an empty queue.
- Decision: `raw_research` has no reducer, so the Researcher returns the
  full merged dict rather than just the new entry.
- Guardrails from the kit went into the Analyst system prompt verbatim in
  spirit: no invented details, no assumed features/pricing, "Data not
  found" for missing fields, concise with no marketing language.
- Robustness: if the Groq call fails for one competitor, the Analyst
  appends a placeholder "Data not found" report and still pops the queue,
  so one bad response doesn't abort the whole run. Researcher/Analyst
  no-op safely if Discovery returns an empty queue.
- LLM is created lazily (`_get_llm`, cached) so importing the module
  doesn't require `GROQ_API_KEY`. Model: `llama-3.3-70b-versatile`, temp 0.
- Verified with an offline smoke test (search + LLM mocked): 3 competitors
  flow through the Researcher -> Analyst loop and produce 3 reports with
  the expected status_log lines.

## Session 5 — Router, graph wiring, Streamlit UI

- Prompt: "Build these files as well graph/nodes.py, then router.py,
  build_graph.py, app.py" (nodes.py was already done in Session 4).
- `graph/router.py`: `queue_router` returns "researcher" while the queue
  has items, else END.
- Decision: the router is also used as a conditional edge right after
  Discovery, not just after the Analyst, so a run with zero competitors
  ends cleanly instead of passing through no-op Researcher/Analyst steps.
- `graph/build_graph.py`: `build_graph()` plus an `initial_state()` helper
  so the UI (and tests) always start with every AgentState key populated.
- `app.py`: uses `graph.stream(..., stream_mode="updates")` instead of
  `invoke()` so each node's `status_log` lines show up live in an
  `st.status` box — matches the kit's live-progress UX. Reports are shown as
  expandable cards (pricing, positioning, features, recent news), and a
  footer notes that human review is the final step.
- Issue found in the first live run: Groq returned 404 for
  `llama-3.3-70b-versatile` — that model has been retired. Listed the
  models on the key and switched the default to `openai/gpt-oss-120b`
  (strongest general model available), made it overridable via a
  `GROQ_MODEL` env var, and documented it in `.env.example`. User
  confirmed keeping `openai/gpt-oss-120b` as the project's model.
- Verified: mocked graph test (3-competitor loop + empty-discovery path),
  live CLI run for "Figma" (Canva, Framer, Sketch; ~17s; correct "Data not
  found" for Sketch's recent news), and a simulated UI run for "Notion"
  via Streamlit's AppTest (3 cards, no errors).
- Observation: discovery quality varies — "Notion" gave Airtable, Craft
  Agents, Scribe. Candidate for prompt/query tuning in the E2E phase.

## Session 6 — README vs. implementation gaps

- Prompt: "Fix these gaps between README.md and the actual implementation:
  (1) correct the model reference to openai/gpt-oss-120b; (2) in
  researcher_node, run the web_search and news_search calls concurrently ...
  and update the README's 'parallel' claim to match reality once it's true;
  (3) move the analyst system prompt out of graph/nodes.py into
  prompts/analyst_prompt.py and import it; (4) add a minimal smoke test in
  tests/test_graph_smoke.py ... Leave docs/architecture.md for now."
- (1) README now names `openai/gpt-oss-120b` as the Groq model.
- (2) `researcher_node` submits both searches to a 2-worker
  `ThreadPoolExecutor`. Chose threads over `asyncio.gather` because the
  graph and Tavily client are synchronous; threads avoid making the whole
  node async for two I/O calls. Verified with two fake searches that each
  sleep 1s: the node takes 1.0s instead of 2s. A live Tavily call for one
  competitor took ~1.7s. README wording changed to "concurrent web + news
  search (both searches run in parallel threads)", which is now accurate.
- (3) `prompts/analyst_prompt.py` holds `ANALYST_SYSTEM_PROMPT` and
  `NOT_FOUND`; `graph/nodes.py` imports both. Added `prompts/__init__.py`
  to match the `graph/` and `tools/` packages. Discovery prompt left in
  `nodes.py` since only the analyst prompt was in scope.
- (4) `tests/test_graph_smoke.py`: offline test that monkeypatches the
  search tools and the LLM factory, runs the compiled graph for "Figma",
  and asserts 3 reports that validate as `CompetitorReport`, an empty
  queue, and the expected search call counts. Added `pytest` to
  `requirements.txt` and a `pytest.ini` (`pythonpath = .`) so
  `python -m pytest` works from the repo root. Result: 1 passed in 0.29s.

## Session 7 — Discovery quality

- Prompt: "Do the discovery improvement first."
- Baseline (old: one query "top competitors and alternatives to X"):
  - Notion -> Airtable, Craft Agents, Scribe
  - Figma -> Canva, Framer, Sketch
  - Slack -> social.plus, Granola, Glue
  - Stripe -> Moneris, Plexo, Trace Finance
  - Zoom -> Webex, Whereby, LiveKit
  - Canva -> Stability AI, Bending Spoons, Juicebox
- Diagnosis: the single search was dominated by CB Insights
  "alternatives" pages, which list niche startups first. The prompt said
  "only use names from the results, most direct first", so the model copied
  that page's order. The Notion results also contained a different "Notion"
  (a smart-lock company), so name collisions were a risk too.
- Changes (all in `graph/nodes.py`):
  - Two differently-phrased queries ("X top competitors", "best X
    alternatives compared") run concurrently and are combined, so no single
    listing site dominates.
  - `CompetitorList` gained a `category` field placed *before*
    `competitors`, so the model states the target's product category and
    customers before picking. Logged to `status_log` so users can see
    what market the agent assumed.
  - Prompt rewritten as steps (identify the product and resolve same-name
    companies, then pick rivals selling the same kind of product to the
    same customers) with rules: prefer established products that appear in
    several sources, don't copy one site's ranking, and exclude
    sub-products, owned companies, and integrations/add-ons. Kept the
    "only names from the search results" grounding rule.
- After:
  - Notion -> Airtable, Coda, ClickUp
  - Figma -> Sketch, Adobe XD, InVision
  - Slack -> Microsoft Teams, Mattermost, Rocket.Chat
  - Stripe -> Adyen, PayPal (Braintree), Checkout.com
  - Zoom -> Microsoft Teams, Google Meet, Cisco Webex
  - Canva -> Adobe Express, Visme, Crello/VistaCreate
- Verified: re-run gave the same picks (Crello vs. VistaCreate is the same
  product after a rebrand); Linear -> Jira, Shortcut, ClickUp; nonsense
  input "asdfqwer" still ends cleanly with no competitors; full live run
  for Notion completed in ~13s with 3 reports; smoke test updated for the
  extra discovery search and still passes.
- Cost: one extra Tavily search per run (2 in Discovery instead of 1).

## Session 8 — Architecture write-up

- Prompt: "Write docs/architecture.md documenting the actual current
  implementation (read the real code ... don't just restate CLAUDE.md,
  since some things there are already stale)", with a set structure:
  overview, diagram, node-by-node breakdown, why the loop works,
  guardrails, human-in-the-loop boundary, deviations from the kit.
- Wrote the doc from the code in `graph/`, `tools/`, `prompts/` and
  `app.py`. It includes a state table (key, type, reducer, which node
  writes it) and explains why `competitor_queue` must *not* use
  `operator.add` (the queue would never empty, so the loop would never
  end) and why `raw_research` is returned as a full merged dict.
- Also documented a subtlety: `stream_mode="updates"` yields each node's
  output before reducers apply, so `app.py` builds up reports and log
  lines itself.
- Deviations section: only the you.com → Tavily and Llama 3.3 70B →
  gpt-oss-120b swaps are described as kit differences. Other changes are
  listed as implementation changes rather than claims about what the kit
  did.
- Fixed a stale diagram in `CLAUDE.md`: it showed Discovery going straight
  to the Researcher, but the router now runs after Discovery too.

## Next up

- Nothing outstanding from the original plan.
