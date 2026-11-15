"""Spatial Fleet: an agent on every machine, a hub that sees the whole fleet.

agent.py  measures its machine continuously, reports to the hub, and runs allow-listed workloads
          the hub hands out (pull model: the agent asks for work, nothing is pushed to it).
hub.py    stores the fleet's measurements, places tasks, and turns the measurements into
          recommendations whose evidence is shown. It never changes a machine by itself.

Everything travels over SWP/2 (encrypted, forward-secret, scoped credentials, audit log).
Savings are only ever ESTIMATES until a recommendation is applied and the fleet is measured again.
"""
def __getattr__(name):                      # lazy: `python -m spatial.fleet.hub` must not import itself twice
    if name == "Agent":
        from .agent import Agent
        return Agent
    if name in ("Hub", "serve_hub"):
        from . import hub
        return getattr(hub, name)
    raise AttributeError(name)
