"""Small stand-ins the decision-loop tests share: a scripted client, a thread that runs inline, an HTTP reply."""
import io

from whitebox_server import SpatialJevClient


class Scripted(SpatialJevClient):
    """Answers the next queued action, else wait (else the first listed option)."""

    def __init__(self, config, moves=()):
        super().__init__(config, key='unit-test-not-a-real-key')
        self.moves, self.asked = list(moves), []

    def ask(self, payload):
        self.asked.append(payload)
        criteria = payload['questions']['next_action']['criteria']
        move = self.moves.pop(0) if self.moves else None
        return {'choice': move if move in criteria else 'wait' if 'wait' in criteria else next(iter(criteria)),
                'sprint': False, 'confidence': None, 'probabilities': {}, 'model': 'test-only', 'usage': {}, 'latency': 0.0}


class Inline:
    """threading.Thread stand-in: runs the target at start, in the caller's thread."""

    def __init__(self, target, daemon=None):
        self.target = target

    def start(self):
        self.target()


class Reply(io.BytesIO):
    """A urllib response stand-in: a body that works as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False
