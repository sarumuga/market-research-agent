# Market Research Agent

A multi-agent competitive market research pipeline built with **LangGraph**,
**LangChain**, **Groq** (`openai/gpt-oss-120b`), **Tavily Search**, and **Streamlit**.

Given a company name, the agent pipeline:
1. **Discovers** that company's top 3 competitors (web search)
2. **Researches** each competitor via concurrent web + news search
   (both searches run in parallel threads)
3. **Analyzes** raw findings into a structured report (pricing, features,
   positioning, recent news) using an LLM with structured output
4. **Displays** results as expandable cards in a Streamlit UI

The workflow intentionally stops after generating reports — no database
writes, emails, or automated actions. Human review is the decision point.

> Adapted from the "Market Research Agent — Solution Kit (Code Track)"
> reference architecture (originally you.com + Groq); this build uses
> Tavily in place of you.com for search.

## Architecture

```
Streamlit UI
     │
     ▼
Discovery Node ──> Researcher Node (loops per competitor) ──> Analyst Node
     │                      ▲                                      │
     │                      └──────── Queue Router ─────────────┐  │
     │                        (loops until queue empty)         │  │
     ▼                                                           ▼  ▼
                                                          Streamlit Report Cards
```

## Project structure

```
market-research-agent/
├── app.py                  # Streamlit UI + graph invocation
├── graph/
│   ├── state.py            # AgentState / CompetitorReport schemas
│   ├── nodes.py            # discovery_node, researcher_node, analyst_node
│   ├── router.py           # queue_router
│   └── build_graph.py      # StateGraph wiring
├── tools/
│   ├── search_client.py    # Tavily API wrapper
│   └── search_tools.py     # LangChain @tool wrappers (web_search, news_search)
├── prompts/
│   └── analyst_prompt.py   # system prompt + guardrails
├── tests/
│   └── test_graph_smoke.py
└── docs/
    ├── architecture.md
    └── prompts_log.md      # vibe-coding prompt log (for course submission)
```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then paste in your real API keys
streamlit run app.py
```

You'll need free/paid API keys from:
- **Groq** — https://console.groq.com
- **Tavily** — https://tavily.com

## Status

🚧 Under active development — see `docs/prompts_log.md` for build history.
