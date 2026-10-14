"""Bounded active-kitchen leases and authenticated-session request budgets.

Called under the session manager lock. Polling does not renew a paused/result
lease. Pending admissions are settled in the handler's finally block.
"""
import time

NETWORK_FULL = 'network'  # reserve(): this network already holds its share of active kitchens.


def network_of(entries, token):
    found = entries.get(token)
    return getattr(found[0], 'network', None) if found else None


class ActiveKitchens:
    def __init__(self, capacity, pause_grace=60, result_grace=30, clock=time.monotonic, per_network=None):
        self.capacity = capacity
        # One network (an address, or an IPv6 /64) may hold at most this many active kitchens.
        self.per_network = per_network
        self.pause_grace, self.result_grace, self.clock = pause_grace, result_grace, clock
        self.leases = {}
        self.rejected = 0
        self.network_rejected = 0

    def refresh(self, entries):
        now = self.clock()
        for token, lease in list(self.leases.items()):
            if token not in entries:
                del self.leases[token]
                continue
            if lease['pending']:
                continue
            phase = entries[token][0].phase
            if phase == 'ready':
                del self.leases[token]
                continue
            if phase != lease['phase']:
                lease.update(phase=phase, until=None if phase == 'running' else
                             now + (self.pause_grace if phase == 'paused' else self.result_grace))
            if lease['until'] is not None and now >= lease['until']:
                del self.leases[token]

    def network_full(self, token, entries):
        network = network_of(entries, token)
        return (self.per_network is not None and network is not None and token not in self.leases and
                sum(network_of(entries, t) == network for t in self.leases) >= self.per_network)

    def reserve(self, token, entries):
        self.refresh(entries)
        if token in self.leases:
            self.leases[token]['pending'] = True
            return False  # Existing lease, not a new allocation.
        if self.network_full(token, entries):
            self.network_rejected += 1
            return NETWORK_FULL
        if len(self.leases) >= self.capacity:
            self.rejected += 1
            return None
        self.leases[token] = {'phase':None, 'until':None, 'pending':True}
        return True

    def settle(self, token, entries, allocated, success):
        lease = self.leases.get(token)
        if not lease:
            return
        if token not in entries:
            del self.leases[token]
            return
        if allocated and not success and entries[token][0].phase != 'running':
            del self.leases[token]
            return
        lease['pending'] = False
        self.refresh(entries)

    def describe(self, token, entries):
        self.refresh(entries)
        network = self.network_full(token, entries)
        full = token not in self.leases and len(self.leases) >= self.capacity
        return {'used':len(self.leases), 'limit':self.capacity, 'per_network':self.per_network,
                'can_start':not network and not full, 'reason':NETWORK_FULL if network else 'full' if full else None,
                'pause_grace_seconds':self.pause_grace, 'result_grace_seconds':self.result_grace}


class RequestBudget:
    def __init__(self, rate=40, burst=40, clock=time.monotonic):
        self.rate, self.burst, self.clock = rate, burst, clock
        self.tokens = burst
        self.last = clock()

    def take(self):
        now = self.clock()
        self.tokens = min(self.burst, self.tokens + max(0, now-self.last)*self.rate)
        self.last = now
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True
