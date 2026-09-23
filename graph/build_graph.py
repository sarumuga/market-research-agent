"""
Wires the nodes and router into a compiled LangGraph StateGraph.

    START -> discovery -> (router) -> researcher -> analyst -> (router)
                             |                                  |
                             +-> END (no competitors)           +-> researcher (queue not empty)
                                                                +-> END        (queue empty)

The graph stops after the last report — human review in the UI is the
final step; there are no DB writes, emails, or other automated actions.
"""

from langgraph.graph import END, START, StateGraph

from graph.nodes import analyst_node, discovery_node, researcher_node
from graph.router import queue_router
from graph.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("discovery", discovery_node)
    graph.add_node("researcher", researcher_node)
    graph.add_node("analyst", analyst_node)

    graph.add_edge(START, "discovery")
    graph.add_conditional_edges(
        "discovery", queue_router, {"researcher": "researcher", END: END}
    )
    graph.add_edge("researcher", "analyst")
    graph.add_conditional_edges(
        "analyst", queue_router, {"researcher": "researcher", END: END}
    )

    return graph.compile()


def initial_state(company_name: str) -> AgentState:
    """Fully-populated starting state for a run."""
    return {
        "company_name": company_name.strip(),
        "competitor_queue": [],
        "raw_research": {},
        "final_reports": [],
        "status_log": [],
    }
