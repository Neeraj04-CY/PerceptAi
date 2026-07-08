"""PerceptAI Runner — a thin worker for distributed execution.

The runner is intentionally minimal: it registers with the control plane,
long-polls for SIGNED work, executes each order through the ONE runtime
(perceptai.AgentSession) without forking any logic, streams canonical wire-v1
events back, heartbeats, and reconnects. It contains no planning, no execution
logic, and no second loop — the engine remains the only execution engine, and
stays unaware that its events and control are crossing a network.
"""
