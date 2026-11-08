"""The environment an agent plays in: what it sees, what it can do, and nothing else (env-v1).

An agent playing a chef gets an AgentPort, never the kitchen itself. The port has two tiers:

- observe() and act(): plain dictionaries, the contract any agent can rely on and Benchmark v1 freezes. observe()
  gives the kitchen state as the engine has it (display-only fields left out, text in English), every action the
  engine lists for the chef right now, unpruned, as {key, kind, target, label}, and the event sequence number;
  events_since(seq) gives the engine events after it. act(key) asks the engine to start that action as it is when
  the request arrives, which is how the game always worked: a choice can be legal when asked and gone when answered.
- view: the engine's own objects, read-only, for agents that run in this process and want them (Jeff's harness
  reads the kitchen this way). Every engine input (start, stop, sprint, advance, set_manual, ...) is refused on the
  view, so whatever an agent does to the kitchen goes through the port and lands in the round's recorded inputs.

Time does not wait for an agent: the session ticks in real time and the port is used from the session's own
thread (Agent.poll), so an agent that thinks for two seconds has spent two seconds of the round.

A change to what observe() returns, to what act() does, or to the timing above bumps ENV_API_VERSION. A change to
how an agent words its prompt, which options it shows its model, or when it asks is the agent's own version.
"""
from __future__ import annotations

ENV_API_VERSION = 'env-v1'
ANY_JOB = object()      # act() without a job guard


class ReadOnlyKitchen:
    """The kitchen, readable and not writable: engine inputs and attribute assignment are refused."""

    __slots__ = ('_kitchen',)

    def __init__(self, kitchen):
        object.__setattr__(self, '_kitchen', kitchen)

    def __getattr__(self, name):
        method = getattr(type(self._kitchen), name, None)
        if getattr(method, '__engine_input__', False):
            raise PermissionError(f'{name} changes the kitchen; an agent acts through its AgentPort')
        return getattr(self._kitchen, name)

    def __setattr__(self, name, value):
        raise PermissionError('the view is read-only; an agent acts through its AgentPort')

    def __repr__(self):
        return f'ReadOnlyKitchen({type(self._kitchen).__name__})'


def _english(value):
    from model_language import english_data
    return english_data(value)


def kitchen_state(snapshot):
    """The engine's snapshot without the fields that only the page draws from (items, route slides, plating art,
    the item art of equipment)."""
    state = {key: value for key, value in snapshot.items() if key != 'items'}
    if 'chefs' in state:
        state['chefs'] = {who: {k: v for k, v in chef.items() if k != 'route_slide'} for who, chef in state['chefs'].items()}
    for key in ('menu', 'dishes'):
        if key in state:
            state[key] = [{k: v for k, v in dish.items() if k != 'plating'} for dish in state[key]]
    if 'equipment' in state.get('map', {}):
        state['map'] = {**state['map'], 'equipment': {key: {k: v for k, v in e.items() if k != 'item'}
                                                       for key, e in state['map']['equipment'].items()}}
    return state


class AgentPort:
    """One chef's way into a kitchen: observe, act, and a read-only view."""

    def __init__(self, kitchen, who='jeff'):
        chefs = getattr(kitchen, 'chefs', None)      # a stand-in kitchen in a test may have none
        if chefs is not None and who not in chefs:
            raise ValueError(f'no chef {who!r} in this kitchen')
        self._kitchen = kitchen
        self.who = who
        self.view = ReadOnlyKitchen(kitchen)

    # Tier 1: plain dictionaries.
    def observe(self):
        k = self._kitchen
        return {'env_api_version': ENV_API_VERSION, 'who': self.who, 'time': round(k.time, 3),
                'event_seq': k.event_seq, 'ended': bool(k.ended),
                'kitchen': _english(kitchen_state(k.snapshot())),
                'actions': [{'key': a.key, 'kind': a.kind, 'target': a.target, 'label': _english(a.label)}
                            for a in k.actions(self.who)]}

    def events_since(self, seq):
        """Engine events after sequence number seq, in English, oldest first."""
        return _english([e for e in self._kitchen.events if e.get('seq', 0) > seq])

    def act(self, key, sprint=False, expect_job=ANY_JOB):
        """Start a listed action now. expect_job: only if the chef is still doing that job id (None: only while idle),
        the guard an agent uses so an answer about one moment is not carried out in another; by default no guard."""
        k = self._kitchen
        if expect_job is not ANY_JOB:
            job = k.chefs[self.who].job
            if (job.id if job else None) != expect_job:
                return {'applied': False, 'reason': 'job_changed', 'job_id': job.id if job else None}
        action = next((a for a in k.actions(self.who) if a.key == key), None)
        if action is None:
            return {'applied': False, 'reason': 'not_listed', 'job_id': self.job_id()}
        applied, message = self.start(action)
        sprinted = bool(applied and sprint and self.sprint())
        return {'applied': bool(applied), 'reason': _english(message), 'sprinted': sprinted, 'job_id': self.job_id()}

    def job_id(self):
        job = self._kitchen.chefs[self.who].job
        return job.id if job else None

    # Engine calls an in-process agent may make with the engine's own action objects (Jeff's loop does).
    def start(self, action):
        """kitchen.start for this chef, with an action from view.actions(): (applied, message)."""
        return self._kitchen.start(self.who, action)

    @property
    def can_sprint(self):
        return hasattr(self._kitchen, 'sprint')

    def sprint(self):
        """Start a sprint if the engine has one and it is ready; whether it started."""
        return bool(self.can_sprint and self._kitchen.sprint(self.who))

    def fork_until_step_end(self):
        """A throw-away copy of the kitchen played on until this chef's current step ends (kitchen.fork), or None
        when the step would not end with action_done; nothing done to it reaches this kitchen."""
        import ask_ahead
        return ask_ahead.predict(self._kitchen, self.who)


class Agent:
    """What an agent implements to play a chef. The session calls poll on its own thread, about 20 times a game
    second; an agent that waits for a model asks in a thread of its own and acts on a later poll."""

    name = 'agent'

    def start(self, port):
        """Once, as the round starts."""

    def poll(self, port, now):
        """Each session tick while the round runs; now is the session's clock in seconds."""

    def close(self):
        """Once, as the round ends or the session closes."""
