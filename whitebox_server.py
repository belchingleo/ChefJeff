"""Jeff's client for the spatial kitchen (every listed level); the local servers are cocos_server.py and hosted_server.py."""
from jev import JevClient
# Candidate pruning moved to harness.py; the name stays importable from here.
from harness import model_candidates  # noqa: F401


class SpatialJevClient(JevClient):
    """Jev client for the spatial kitchen: harness.payload adds its rules, pruning and sprint question."""
    spatial = True
