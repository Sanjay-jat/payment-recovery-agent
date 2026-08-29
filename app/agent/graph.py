"""
Wires all nodes into the LangGraph state machine.
"""

from langgraph.graph import StateGraph, END

from app.agent.state import RecoveryState
from app.agent.nodes import detect_decline, decide_action, compliance_gate, execute, track_outcome


def should_continue(state: RecoveryState) -> str:
    """Conditional edge: loop back to decide_action, or end."""
    if state["status"] == "pending" and state["retry_count"] < state["max_retries"]:
        return "decide_action"
    return END


def build_graph():
    graph = StateGraph(RecoveryState)

    graph.add_node("detect_decline", detect_decline)
    graph.add_node("decide_action", decide_action)
    graph.add_node("compliance_gate", compliance_gate)
    graph.add_node("execute", execute)
    graph.add_node("track_outcome", track_outcome)

    graph.set_entry_point("detect_decline")
    graph.add_edge("detect_decline", "decide_action")
    graph.add_edge("decide_action", "compliance_gate")
    graph.add_edge("compliance_gate", "execute")
    graph.add_edge("execute", "track_outcome")

    graph.add_conditional_edges("track_outcome", should_continue)

    return graph.compile()


app_graph = build_graph()