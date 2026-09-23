# Architecture

## Overview

The user enters a company name in a Streamlit UI. A LangGraph pipeline then
runs three agent nodes over shared state. **Discovery** searches the web and
asks an LLM to name the company's product category and its top 3 direct
competitors. **Researcher** runs a web search and a news search, at the same
time, for one competitor. **Analyst** turns that raw search text into a
structured `CompetitorReport` (pricing, core features, market positioning,
recent news) using Groq structured output. A queue router loops the
Researcher → Analyst pair once per competitor, then ends the run. The UI
streams progress messages while the graph runs and shows one card per
report. The graph stops there: a human reviews the reports, and the system
takes no action based on them.

**Stack:** LangGraph (orchestration), LangChain (tool and LLM wrappers),
Groq `openai/gpt-oss-120b` (LLM), Tavily (search), Pydantic (schemas),
Streamlit (UI).

## Architecture diagram

```
                      Streamlit UI (app.py)
                               │ initial_state(company)
                               ▼
 START ──► discovery_node ──► queue_router ──(queue empty)──► END
                                   │
                           (queue not empty)
                                   ▼
                  ┌──────► researcher_node      web_search ┐ run concurrently
                  │                │            news_search┘ (ThreadPoolExecutor)
                  │                ▼
                  │          analyst_node       Groq structured output
                  │                │            → CompetitorReport, pops queue
                  │                ▼
                  └─(not empty)─ queue_router ──(queue empty)──► END
                                                                  │
                            UI renders final_reports as cards ◄───┘
                            (human review)
```

The graph is wired in `graph/build_graph.py`. `queue_router` is attached as
a conditional edge after **both** `discovery` and `analyst`. If Discovery
finds no competitors, the run goes straight to END instead of passing
through empty Researcher and Analyst steps.

## Shared state

`graph/state.py` defines the state object that every node reads from and
writes to:

| Key | Type | Reducer | Written by |
|---|---|---|---|
| `company_name` | `str` | none (overwrite) | UI, via `initial_state()` |
| `competitor_queue` | `list[str]` | none (overwrite) | Discovery (fills it), Analyst (pops it) |
| `raw_research` | `dict[str, str]` | none (overwrite) | Discovery (resets it), Researcher (adds an entry) |
| `final_reports` | `list[dict]` | `operator.add` | Analyst |
| `status_log` | `list[str]` | `operator.add` | every node |

`CompetitorReport` (Pydantic) has these fields: `competitor_name`,
`pricing_model`, `core_features: list[str]`, `market_positioning`,
`recent_news`. Each field's description is part of the schema sent to the
LLM; the `pricing_model` and `recent_news` descriptions tell the model to
use "Data not found" when the data is missing.

## Node-by-node breakdown

Each node returns a *partial* state dict, which LangGraph merges into the
state. Every node also adds at least one human-readable line to
`status_log`.

### `discovery_node` (`graph/nodes.py`)

- **Reads:** `company_name`.
- **Does:**
  1. Runs two differently-phrased web searches at the same time
     (`DISCOVERY_QUERIES`: `"{company} top competitors"`,
     `"best {company} alternatives compared"`). Two phrasings keep a single
     listing site from dominating the evidence.
  2. Sends the combined results to Groq with
     `with_structured_output(CompetitorList)`. `CompetitorList` has a
     `category` field *before* `competitors`, so the model first names the
     target's product category and customers, then picks competitors. The
     prompt tells it to:
     - use only names that appear in the search results;
     - prefer established products named by several sources;
     - not copy any one site's ranking;
     - exclude sub-products, companies the target owns, and add-ons;
     - pick the best-known company when several share the target's name.
  3. Post-processes the list in code: removes duplicates (ignoring case),
     removes the target company, and keeps at most 3 names.
- **Returns:** `competitor_queue` (0 to 3 names), `raw_research: {}`, and
  `status_log`, which includes the category line so the user can see which
  market the agent assumed.

### `researcher_node` (`graph/nodes.py`)

- **Reads:** `competitor_queue[0]` (it does not pop the queue) and the
  existing `raw_research`.
- **Does:** runs `web_search("<name> pricing features target market")` and
  `news_search("<name> launch funding partnership")` **concurrently**, in a
  2-worker `ThreadPoolExecutor`. The two calls are independent network
  requests, so the step takes about as long as the slower one instead of
  both combined. With two fake searches that each take 1 s, the node
  finishes in 1.0 s rather than 2 s. Threads were chosen over `asyncio`
  because the graph and the Tavily client are synchronous.
- **Returns:** `raw_research` as a *full merged dict* (existing entries plus
  `{name: "WEB RESULTS: ... NEWS RESULTS: ..."}`) and `status_log`. If the
  queue is empty, it returns only a log line.

Search goes through `tools/search_tools.py` (LangChain `@tool` wrappers),
which calls `tools/search_client.py` (`SearchClient`: Tavily,
`search_depth="basic"`, 5 results per query). The web/news split maps to
Tavily's `topic="general"` and `topic="news"`. Results are formatted as
numbered text blocks with title, URL and snippet, not raw JSON.

### `analyst_node` (`graph/nodes.py`)

- **Reads:** `competitor_queue`, `raw_research[competitor]`, and
  `company_name`.
- **Does:** calls Groq with `with_structured_output(CompetitorReport)`,
  using `ANALYST_SYSTEM_PROMPT` (from `prompts/analyst_prompt.py`) and the
  competitor's raw research. It then sets `competitor_name` to the name from
  the queue rather than trusting the LLM's echo. If the LLM call fails, it
  produces a placeholder report with every field set to "Data not found",
  so one bad response doesn't abort the whole run.
- **Returns:** `competitor_queue: queue[1:]` (the pop), `final_reports:
  [report]`, and `status_log`.

Only the Analyst pops the queue. The Researcher and Analyst therefore
always agree on which competitor is current (`competitor_queue[0]`), and the
router only has to check whether the queue is empty.

### `queue_router` (`graph/router.py`)

- **Reads:** `competitor_queue`.
- **Does:** returns `"researcher"` if the queue is non-empty, otherwise
  `END`.
- **Returns:** a routing decision, not a state update.

The LLM client is created on first use (`_get_llm`, cached,
`temperature=0`), so the module can be imported, for example by tests,
without API keys.

## Why the loop works

In LangGraph, when a node returns a key, the default is to **overwrite**
that key's value. A key annotated with a reducer, such as
`Annotated[list[dict], operator.add]`, is **combined** instead:
`new_state[key] = old_value + returned_value`.

The Researcher → Analyst pair runs once per competitor, and each Analyst
pass returns only `final_reports: [this_report]`. Without the reducer, the
third pass would overwrite the first two reports and the run would end with
a single report. With `operator.add`, the lists are concatenated
(`[] + [r1] + [r2] + [r3]`) and the final state holds all three.
`status_log` uses the same reducer so that every node's messages build up
into one run history.

The other two mutable keys should *not* accumulate:

- **`competitor_queue`** should be replaced. The Analyst returns
  `queue[1:]` as the new queue. With `operator.add`, each pass would
  *append* the remaining names (`[A,B,C] + [B,C]`), so the queue would never
  empty and the loop would never end.
- **`raw_research`** is a dict, and `operator.add` isn't defined for dicts.
  The Researcher reads the existing dict, adds one entry and returns the
  whole merged dict, so overwriting is correct. Discovery resets it to `{}`
  at the start of a run.

The UI uses `graph.stream(..., stream_mode="updates")`. That mode yields
each node's partial output *before* reducers are applied, so `app.py`
builds up the `status_log` lines and `final_reports` itself as updates
arrive. This is what lets progress show live instead of only at the end.

## Guardrails

`prompts/analyst_prompt.py` limits the Analyst to the research text:

- Build the report "using ONLY the research provided".
- Do not invent competitor details that are not in the research.
- Do not assume features or pricing; if pricing isn't stated, use
  "Data not found".
- Use "Data not found" for any field the research doesn't support.
- `core_features`: 3–5 short items from the research, or
  `["Data not found"]`.
- Be concise and factual, with no marketing language or superlatives.

**Why these rules matter.** An LLM asked to fill every field of a schema
will otherwise fill gaps from its own training data. For pricing,
features and recent news that data may be out of date or simply invented,
and the structured output makes invented values look just as authoritative
as real ones. Giving the model an explicit "Data not found" value makes
"no answer" something the model is allowed to return, so a gap in the
sources shows up as a gap in the report instead of a guess. For
`pricing_model` and `recent_news`, the Pydantic field descriptions repeat
the "Data not found" instruction, so the model sees it in both the prompt
and the schema. Banning marketing language keeps the model from copying promotional
wording from vendor pages. In testing, fields with no supporting source
(for example, recent news for Sketch in one run) correctly came back as
"Data not found".

Discovery has the same grounding rule: it may only return names that
appear in the search results.

**Limits.** These are prompt-level controls, not verification. The system
does not check each claim against the source text, and it does not show
which URL supports each field. That is why the output goes to a human
reviewer.

## Human-in-the-loop boundary

The graph ends at END after the last report. The system deliberately does
**not**:

- write to a database or save reports anywhere; results exist only in the
  Streamlit session;
- send emails, messages or notifications;
- take any automated action (pricing changes, CRM updates, alerts) based on
  its findings.

The human review step is the report view in `app.py`. The reports are
shown as expandable cards with a note that they "are generated from search
results and may be incomplete. Review before acting on them." Any decision
based on the reports is made by the user, outside the system.

## Deviations from the reference kit

This build keeps the kit's three-node + queue-router design, its
guardrails and its live-progress UX. It swaps two external services:

| Area | Reference kit | This build | Why |
|---|---|---|---|
| Search provider | you.com | Tavily (`tavily-python`) | Free tier and a simpler API. Its `topic="general"` / `topic="news"` switch covers the web/news split directly. It sits behind `SearchClient`, so the provider can be swapped without touching the tool or graph code. |
| LLM | Groq, Llama 3.3 70B | Groq, `openai/gpt-oss-120b` | Llama 3.3 70B has been retired on Groq; the first live run returned a 404 `model_not_found`. `gpt-oss-120b` is the strongest general model available on Groq. It can be changed with `GROQ_MODEL` in `.env`. |

Other changes made during implementation (full history in
`docs/prompts_log.md`):

- **Concurrent searches.** The Researcher runs its web and news searches in
  parallel threads, and Discovery does the same for its two queries.
- **Discovery quality.** The first version ran one query and copied a
  single database's list of niche startups (e.g. Slack → social.plus,
  Granola, Glue). The current version uses two queries, a category-first
  `CompetitorList`, a stricter selection prompt, and dedupe and exclusion in
  code. Slack now gives Microsoft Teams, Mattermost, Rocket.Chat (Session 7
  has the full before/after lists).
- **Router placement.** `queue_router` also runs after Discovery, so a run
  with zero competitors ends cleanly.
- **Analyst failure handling.** A failed LLM call produces a "Data not
  found" placeholder report and the loop continues.
- **Prompt location.** The Analyst prompt is in `prompts/analyst_prompt.py`
  so the guardrails can be reviewed apart from the graph code. The
  Discovery prompt is still in `graph/nodes.py`.
- **Streaming UI.** `graph.stream(stream_mode="updates")` feeds `st.status`,
  so messages appear as each node finishes.
- **Offline smoke test.** `tests/test_graph_smoke.py` fakes search and the
  LLM and checks the loop and reducers without API keys: 3 valid reports,
  empty queue, expected search call counts.

**Cost per run** (3 competitors): 8 Tavily searches (2 for Discovery,
plus 2 per competitor) and 4 Groq calls (1 for Discovery, plus 1 per
competitor). A typical live run takes 13–17 s.
