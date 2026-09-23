"""
Streamlit UI for the market research pipeline.

Enter a company name, click "Run Research Pipeline", watch the live
status log as each node runs, then review the competitor report cards.
The app only displays results — human review is the final step.

Run with:  streamlit run app.py
"""

import os

import streamlit as st
from dotenv import load_dotenv

# Load keys before anything touches Groq/Tavily.
load_dotenv()

from graph.build_graph import build_graph, initial_state  # noqa: E402

NOT_FOUND = "Data not found"

st.set_page_config(page_title="Market Research Agent", page_icon="🔎", layout="wide")


@st.cache_resource
def get_graph():
    return build_graph()


def missing_keys() -> list[str]:
    return [k for k in ("GROQ_API_KEY", "TAVILY_API_KEY") if not os.getenv(k)]


def render_report(report: dict) -> None:
    with st.expander(f"**{report['competitor_name']}**", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Pricing model**")
            st.write(report["pricing_model"])
            st.markdown("**Market positioning**")
            st.write(report["market_positioning"])
        with col2:
            st.markdown("**Core features**")
            features = report.get("core_features") or [NOT_FOUND]
            st.markdown("\n".join(f"- {f}" for f in features))
            st.markdown("**Recent news**")
            st.write(report["recent_news"])


st.title("🔎 Competitive Market Research Agent")
st.caption(
    "Discovers the top 3 competitors for a company, researches each via web "
    "and news search, and produces structured reports for human review."
)

if missing := missing_keys():
    st.error(
        f"Missing API key(s): {', '.join(missing)}. "
        "Copy `.env.example` to `.env` and add your keys, then restart the app."
    )
    st.stop()

company = st.text_input("Company name", placeholder="e.g. Figma")
run = st.button("Run Research Pipeline", type="primary", disabled=not company.strip())

if run:
    reports: list[dict] = []
    log_lines: list[str] = []

    with st.status(f"Researching competitors of '{company.strip()}'...", expanded=True) as status:
        try:
            # stream_mode="updates" yields {node_name: partial_state} after
            # each node, which lets us show status_log lines as they happen.
            for update in get_graph().stream(
                initial_state(company), stream_mode="updates"
            ):
                for node_output in update.values():
                    if not node_output:
                        continue
                    for line in node_output.get("status_log", []):
                        log_lines.append(line)
                        st.write(line)
                    reports.extend(node_output.get("final_reports", []))
        except Exception as exc:
            status.update(label="Pipeline failed", state="error")
            st.exception(exc)
            st.stop()

        status.update(
            label=f"Done: {len(reports)} competitor report(s) generated",
            state="complete",
            expanded=False,
        )

    st.session_state["results"] = {
        "company": company.strip(),
        "reports": reports,
        "log": log_lines,
    }

# Keep the last results on screen across Streamlit reruns.
results = st.session_state.get("results")
if results:
    st.subheader(f"Competitor reports for {results['company']}")
    if not results["reports"]:
        st.warning("No competitors were found. Try a more specific company name.")
    for report in results["reports"]:
        render_report(report)
    st.info(
        "These reports are generated from search results and may be incomplete. "
        "Review before acting on them."
    )
