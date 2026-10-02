"""Item provenance: which completed actions touched which items, and what each served dish is made of.

The tracker only reads the kitchen around each completed job; it does not change
events, snapshots or engine behaviour, so replays and fingerprints are unaffected.
A replayed session rebuilds the same provenance because the engine is deterministic.

For every completed job it compares where each item is (and in what state) before
and after, and records a touch for every item that moved, changed or appeared.
Items that disappear into a plate become parents of that dish; a served dish keeps
its components' histories, cut at the moment they were merged.
"""
from dataclasses import dataclass, field

# Completed actions that count as "actions" for collaboration analysis
# (owner decision 2026-09-28): walking and waiting are not actions.
NON_ACTIONS = frozenset({'go', 'wait', 'stop', 'continue'})
PENALTY_EVENTS = {'wrong_dish': 'wrong_dish', 'dish_rejected': 'refused', 'bad_service': 'bad_service'}
PENALIZED_KINDS = {'discard': 'discard', 'clear': 'clear', 'empty_pot': 'empty_pot'}


@dataclass
class Touch:
    seq: int            # global order of completed-job steps
    action_ids: tuple   # every job completed in this step (shared chopping completes two)
    actors: tuple
    kind: str
    place: str          # where the item is after the step ('' when it left the kitchen)
    state: tuple        # (stage, components, contents id) after the step


@dataclass
class Merge:
    dish: str           # item id of the plate after the merge
    parent: str         # item that disappeared into it
    upto: int           # parent's history index at the merge (exclusive)
    seq: int            # step of the merge


@dataclass
class Provenance:
    history: dict = field(default_factory=dict)      # item id -> [Touch]
    merges: list = field(default_factory=list)       # [Merge]
    containers: list = field(default_factory=list)   # [Merge]: food entering a pot; parent is the pot
    actions: dict = field(default_factory=dict)      # action id -> {actor, kind, key, t, seq}
    serves: list = field(default_factory=list)       # {action_id, item, plate, outcome, t}
    penalties: dict = field(default_factory=dict)    # action id -> reason
    ingredients: dict = field(default_factory=dict)  # item id -> recipe item it is (beef, bread, ...)
    steps: int = 0

    def locate(self, k):
        """Where every item is: id -> (place, state)."""
        out = {}

        def add(food, place):
            if food is None:
                return
            if food.stage not in ('pot', 'clean_plate', 'dirty_plate', 'extinguisher') and not food.plate_id:
                self.ingredients.setdefault(food.id, food.ingredient)
            out[food.id] = (place, (food.stage, tuple(food.components or ()),
                                    food.contents.id if food.contents else None))
            if food.contents is not None:
                add(food.contents, f'in:{food.id}')

        for key, s in k.stations.items():
            if getattr(s, 'pot_id', None):
                out[s.pot_id] = (f'st:{key}', ('pot', (), s.food.id if s.food else None))
            add(s.food, f'st:{key}')
        for who, chef in k.chefs.items():
            add(chef.hand, f'hand:{who}')
        for item in getattr(k, 'ground', {}).values():
            add(item.food, f'gr:{item.location}')
        for p in getattr(k, 'projectiles', {}).values():
            add(p['food'], 'air')
        for d in getattr(k, 'dining', []):
            add(d['plate'], 'dining')
        return out

    def around_finish(self, k, who, job, finish):
        before = self.locate(k)
        first_event = len(k.events)
        held = k.chefs[who].hand
        finish()
        after = self.locate(k)
        done = [e for e in k.events[first_event:] if e.get('kind') == 'action_done' and e.get('action_id')]
        if not done:
            return
        self.steps += 1
        ids = tuple(e['action_id'] for e in done)
        actors = tuple(e['actor'] for e in done)
        # Every completion in one step shares the job's kind (a shared chop completes both chefs).
        # Where each chef stood when the step finished (spatial kitchens): the analyzer measures the
        # shortest walk a carried item needed between two steps from these points.
        positions = getattr(k, 'positions', None) or {}
        for e in done:
            at = positions.get(e['actor'])
            self.actions[e['action_id']] = {'actor': e['actor'], 'kind': job.action.kind, 'key': e.get('action'),
                                            't': e['t'], 'seq': self.steps,
                                            'at': (round(at[0], 3), round(at[1], 3)) if at else None}
        for e in k.events[first_event:]:
            reason = PENALTY_EVENTS.get(e.get('kind'))
            if reason and e.get('action_id'):
                self.penalties[e['action_id']] = reason
        if job.action.kind in PENALIZED_KINDS:
            self.penalties.setdefault(job.id, PENALIZED_KINDS[job.action.kind])
        changed = {i for i in set(before) | set(after) if before.get(i) != after.get(i)}
        for item in sorted(changed):
            place, state = after.get(item, ('', ()))
            self.history.setdefault(item, []).append(Touch(self.steps, ids, actors, job.action.kind, place, state))
        vanished = [i for i in before if i not in after]
        # Food entering a pot: the pot's handling since it was last emptied made this cooking possible.
        for pot in changed:
            if pot in after and after[pot][1][0] == 'pot':
                inside, previous = after[pot][1][2], before.get(pot, (None, (None, (), None)))[1][2]
                if inside and inside != previous:
                    self.containers.append(Merge(inside, pot, len(self.history.get(pot, [])), self.steps))
        grown = [i for i in changed if i in after and before.get(i, (None, (None, ())))[1][1] != after[i][1][1]
                 and after[i][1][1]]
        if job.action.kind == 'serve' and held is not None:
            outcome = next((PENALTY_EVENTS[e['kind']] for e in k.events[first_event:] if e.get('kind') in PENALTY_EVENTS), 'served')
            self.serves.append({'action_id': job.id, 'item': held.id, 'plate': held.plate_id, 'outcome': outcome,
                                'dish': k.dish(held),
                                't': round(k.time, 3), 'actor': who})
        elif grown:
            for dish in grown:
                for parent in vanished:
                    self.merges.append(Merge(dish, parent, len(self.history.get(parent, [])), self.steps))
