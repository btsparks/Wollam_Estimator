"""Agent runner — orchestrates single and batch agent execution."""

from app.agents import AGENT_REGISTRY


def run_agent(agent_name: str, bid_id: int, progress_callback=None) -> dict:
    """Run a single agent against a bid.

    Args:
        agent_name: Key from AGENT_REGISTRY (e.g., 'legal').
        bid_id: The bid to analyze.
        progress_callback: Optional callable(message: str).

    Returns:
        The agent's parsed report dict.

    Raises:
        KeyError: If agent_name is not in the registry.
    """
    agent_cls = AGENT_REGISTRY.get(agent_name)
    if not agent_cls:
        raise KeyError(f"Unknown agent: {agent_name}. Available: {list(AGENT_REGISTRY.keys())}")

    agent = agent_cls()
    return agent.run(bid_id, progress_callback=progress_callback)


def run_all_agents(bid_id: int, progress_callback=None) -> dict[str, dict]:
    """Run all agents sequentially against a bid.

    Document Control runs first, then the rest in registry order.

    Args:
        bid_id: The bid to analyze.
        progress_callback: Optional callable(message: str).

    Returns:
        Dict of {agent_name: report_dict}. Agents that error will have
        {"error": "message"} instead of a report.
    """
    results = {}

    for agent_name, agent_cls in AGENT_REGISTRY.items():
        agent = agent_cls()
        try:
            report = agent.run(bid_id, progress_callback=progress_callback)
            results[agent_name] = report
        except Exception as e:
            results[agent_name] = {"error": str(e)}
            if progress_callback:
                progress_callback(f"{agent.AGENT_DISPLAY_NAME}: ERROR — {e}")

    return results
