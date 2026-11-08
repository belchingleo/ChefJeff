"""Run any environment.Agent in the game's session, where Jeff's DecisionLoop would run.

The session (web_server.GameSession) treats its loop as Jeff's: it reads call counts, tokens and errors from it,
invalidates it on a pause and closes it at the end. AgentLoop keeps that surface (as a DecisionLoop with no model
client) and hands each tick to the agent through its AgentPort. Every action the agent starts is an engine input,
so the round's journal, bundle and replay need nothing more; what the agent thinks is its own to record.
"""
from __future__ import annotations
import time

from jev import DecisionLoop


class AgentLoop(DecisionLoop):
    def __init__(self, kitchen, agent, log, notify):
        self._closed = False
        super().__init__(kitchen, None, log, notify)
        self.agent = agent
        self.started = False
        self.actual_model = getattr(agent, 'name', type(agent).__name__)

    @property
    def closed(self):
        return self._closed

    @closed.setter
    def closed(self, value):
        """The session closes its loop as the round ends: the agent hears it once."""
        if value and not self._closed and getattr(self, 'started', False):
            self.agent.close()
        self._closed = value

    def poll(self, enabled=True):
        if not enabled or self.closed or self.k.ended:
            return
        if not self.started:
            self.started = True
            self.agent.start(self.port)
        self.agent.poll(self.port, time.monotonic())
