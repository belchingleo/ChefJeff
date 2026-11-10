"""A test client that answers queued replies (shared by the option_links tests)."""
from whitebox_server import SpatialJevClient


class Answering(SpatialJevClient):
    def __init__(self, config, replies=()):
        super().__init__(config, key='unit-test-not-a-real-key')
        self.replies, self.asked = list(replies), []

    def ask(self, payload):
        self.asked.append(payload)
        criteria = payload['questions']['next_action']['criteria']
        reply = self.replies.pop(0) if self.replies else {}
        choice = reply.get('choice') if reply.get('choice') in criteria else ('continue' if 'continue' in criteria else 'wait')
        return {'choice': choice, 'sprint': False, 'confidence': None, 'probabilities': {}, 'model': 'test-only',
                'usage': {}, 'latency': 0.0}
