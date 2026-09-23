"""
Conditional-edge router for the Researcher -> Analyst loop.

The Analyst pops one competitor off competitor_queue per pass, so the
router only needs to check whether anything is left: loop back to the
Researcher if so, otherwise finish. Also used right after Discovery so
an empty discovery result goes straight to END.
"""

from typing import Literal

from langgraph.graph import END

from graph.state import AgentState


def queue_router(state: AgentState) -> Literal["researcher", "__end__"]:
    if state.get("competitor_queue"):
        return "researcher"
    return END
