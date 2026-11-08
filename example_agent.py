"""A minimal agent that plays Jeff through the environment's plain interface only (env-v1).

It shows the whole contract a new agent needs: environment.Agent's start, poll and close, and the port's observe()
and act(). It does not import Jeff's harness or any model client. Its policy is deliberately simple: by what the chef
holds, it takes the first listed action that is the next step of a dish (NEXT), reading the observation only to
skip what is not ready yet, else waits. It is a floor to beat, not a cook: it serves steaks on levels 1 and 3 and
does little with level 2's burgers. `think` makes
it answer that many seconds after it looks, the way a model would, so the kitchen moves on while it thinks; the
answer carries the job it was about (expect_job), so an answer about one moment is not carried out in another.

    from example_agent import PriorityAgent
    GameSession(config, client_factory=lambda config: PriorityAgent(think=1.0), ...)
"""
from __future__ import annotations

import environment

# What to do next, by what the chef holds: the steps of a dish in order, nothing that costs money (discard, emptying
# a pot) or puts things on the floor (drop, throw).
NEXT = {
    None: ('wash', 'take_board', 'take_counter', 'chop', 'take_sink', 'take_plate', 'take_return', 'fetch'),
    'raw': ('put_board',),
    'chopped': ('put_pot', 'assemble', 'put_counter'),      # a counter while every pan is busy
    'clean_plate': ('plate_pot', 'assemble', 'put_counter'),
    'plated': ('serve',),
    'dirty_plate': ('put_sink',),
    'pot': ('return_pot',),
}


class PriorityAgent(environment.Agent):
    name = 'example-priority-agent'

    def __init__(self, think=0.0):
        self.think = think
        self.pending = None         # (due, key, job it was decided for)
        self.acted = 0

    def start(self, port):
        self.pending = None

    def holding(self, seen, who):
        """What the chef holds, as NEXT's keys: None, raw, chopped, clean_plate, plated, dirty_plate, pot."""
        held = seen['kitchen']['chefs'][who].get('holding')
        if not held:
            return None
        if held.get('plate_id') or held.get('stage') == 'assembled':
            return 'plated'
        return held.get('stage')

    def useful(self, action, seen):
        """Read the state the action is about, so it only takes what is ready and fetches only what has room."""
        stations = seen['kitchen']['stations']
        foods = [s.get('food') or {} for s in stations.values()]
        if action['kind'] == 'take_board':
            return ((stations.get(action['target']) or {}).get('food') or {}).get('stage') == 'chopped'
        if action['kind'] == 'take_counter':                     # parked chopped food, once a pan is free for it
            parked = ((stations.get(action['target']) or {}).get('food') or {}).get('stage') == 'chopped'
            return parked and any(s.get('stove') and not s.get('food') for s in stations.values())
        if action['kind'] == 'take_plate':                       # a plate only when there is cooked food to put on it
            return any(f.get('stage') == 'ready' for f in foods)
        if action['kind'] == 'fetch':                            # a new ingredient only while a board is free
            return any(s.get('type') == 'board' and not s.get('food') for s in stations.values())
        return True

    def choose(self, seen, who):
        """The first useful listed action for what the chef holds, or wait."""
        for kind in NEXT.get(self.holding(seen, who), ()):
            for action in seen['actions']:
                if action['kind'] == kind and self.useful(action, seen):
                    return action['key']
        return 'wait'

    def poll(self, port, now):
        if self.pending and now >= self.pending[0]:
            _, key, job = self.pending
            self.pending = None
            if key != 'wait' and port.act(key, expect_job=job)['applied']:
                self.acted += 1
            return
        if self.pending is None:
            seen = port.observe()
            if seen['kitchen']['chefs'][port.who].get('job_id') is None:      # idle: decide what to do next
                self.pending = (now + self.think, self.choose(seen, port.who), None)

    def close(self):
        self.pending = None
