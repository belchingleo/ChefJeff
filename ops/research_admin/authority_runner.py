#!/usr/bin/env python3
"""Run the unchanged game release's authority, adding a separate source index only."""
from pathlib import Path
import sys

# This runner is a separate service entry point. The game current link is never changed.
release = Path('/opt/chefjeff/current').resolve(strict=True)
sys.path.insert(0,str(release))
import shared_server
from source_observer import observed_classes

shared_server.DataHandler, shared_server.DataServer = observed_classes(shared_server)
if __name__ == '__main__':
    shared_server.main()
