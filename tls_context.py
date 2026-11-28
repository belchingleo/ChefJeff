"""One verified TLS setup per process for the model and data clients.

Making a TLS client context loads the system's certificate bundle, about 10-20 ms of CPU each time (2026-11-28, on a
Mac with Python 3.12). The clients that build an opener or a connection per request made one for every request:
player_api's chat client, the online server's Jev, Cloudflare and free-model forwarders, the free-model gateway
client and the shared data client. They now share one, made the way each made its own, so the connection is the same:
certificates and host names checked, a new connection per request (no keep-alive, no retries), the same handshake
and headers.

- urllib_context() is the context urllib's default HTTPS handler makes for every opener on this Python
  (urllib.request.HTTPSHandler with no context; since 3.10 it offers ALPN "http/1.1"; post-handshake authentication on);
- context() is ssl.create_default_context(), which the two http.client clients pass.

Each is made on first use, so it reads the certificate settings (SSL_CERT_FILE, ...) then, and again after LIFETIME
seconds, so a certificate added to or removed from the system's store reaches the clients within that time, as it
reached every request before. A request that fails certificate verification through https_handler() drops the shared
urllib context at once, so the player's retry after installing a missing root certificate loads the store afresh, as
before. A setup that fails is tried again on the next request.
"""
from __future__ import annotations

import http.client
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request

LIFETIME = 300.0            # seconds a shared context is kept before the certificate store is read again
_lock = threading.Lock()
_made = {}                  # name -> (context, monotonic time it was made)


def _shared(name, make):
    with _lock:
        held = _made.get(name)
        if held is None or time.monotonic() - held[1] >= LIFETIME:
            held = _made[name] = (make(), time.monotonic())
        return held[0]


def forget(name=None):
    """Make the shared context (or all of them) afresh on next use."""
    with _lock:
        if name is None:
            _made.clear()
        else:
            _made.pop(name, None)


def _urllib_like():
    """The context urllib's HTTPSHandler (and http.client.HTTPSConnection) makes when given none, on this Python."""
    version = http.client.HTTPSConnection._http_vsn
    make = getattr(http.client, '_create_https_context', None)
    if make is not None:                    # 3.12+: the function urllib's handler calls
        return make(version)
    made = ssl._create_default_https_context()
    if sys.version_info >= (3, 10) and version == 11:      # 3.10/3.11 HTTPSConnection; 3.8/3.9 offer no ALPN
        made.set_alpn_protocols(['http/1.1'])
    if made.post_handshake_auth is not None:
        made.post_handshake_auth = True
    return made


def context() -> ssl.SSLContext:
    """The process's ssl.create_default_context(), made once per LIFETIME."""
    return _shared('default', ssl.create_default_context)


def urllib_context() -> ssl.SSLContext:
    """The process's copy of the context urllib's default HTTPS handler makes per opener, made once per LIFETIME."""
    return _shared('urllib', _urllib_like)


def _verification_failed(error):
    reason = getattr(error, 'reason', error)
    return isinstance(reason, ssl.SSLCertVerificationError)


class SharedHTTPSHandler(urllib.request.HTTPSHandler):
    """urllib's HTTPS handler on urllib_context(); after a certificate-verification failure the context is dropped."""

    def https_open(self, req):
        try:
            return super().https_open(req)
        except (urllib.error.URLError, ssl.SSLError) as error:
            if _verification_failed(error):
                forget('urllib')
            raise


def https_handler() -> urllib.request.HTTPSHandler:
    """An HTTPS handler on urllib_context(), for urllib.request.build_opener (one opener per request, as before)."""
    return SharedHTTPSHandler(context=urllib_context())
