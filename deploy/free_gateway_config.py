"""Pure reviewed config renderers; no secrets, writes, restarts or database access."""
import ipaddress
from pathlib import Path
import re

INCLUDE = '    include /etc/chefjeff-free/nginx-location.conf;\n'


def nginx_location(peer='2.31.58.179', port=8798):
    peer = str(ipaddress.ip_address(peer))
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid gateway port')
    return '''location ^~ /v1/free-models/ {
    allow PEER;
    allow 127.0.0.1;
    deny all;
    access_log off;
    error_log /dev/null;
    client_max_body_size 256k;
    client_body_buffer_size 256k;
    proxy_http_version 1.1;
    proxy_request_buffering off;
    proxy_buffering off;
    proxy_max_temp_file_size 0;
    proxy_read_timeout 25s;
    proxy_pass http://127.0.0.1:PORT;
}
'''.replace('PEER', peer).replace('PORT', str(port))


def data_candidate(text):
    if not re.search(r'\bserver_name\s+data\.belchingleo\.online\s*;', text):
        raise ValueError('Unexpected data hostname')
    if text.count('    location /v1/ {') != 1 or '/v1/free-models/' in text or INCLUDE.strip() in text:
        raise ValueError('Unexpected existing gateway route')
    return text.replace('    location /v1/ {', INCLUDE+'    location /v1/ {', 1)


# The later free models: their own private key file, enabled only by an explicit, reviewed unit.
EXTRA_KEYS = '/etc/chefjeff-free/extra-model-keys.json'
EXTRA_FLAGS = ' --extra-keys-file ' + EXTRA_KEYS + ' --extra-models-verified'


def gateway_unit(release, extra_models=False):
    path = Path(release)
    if not path.is_absolute() or not re.fullmatch(r'/opt/chefjeff/releases/[a-z0-9-]+/chefjeff-web-demo', str(path)):
        raise ValueError('Use a staged, immutable game release')
    return '''[Unit]
Description=ChefJeff shared free model gateway
After=network-online.target
Wants=network-online.target

[Service]
User=chefjeff-free
Group=chefjeff-free
WorkingDirectory=RELEASE
ExecStart=/usr/bin/python3 RELEASE/free_model_gateway.py serve --port 8798 --state-dir /var/lib/chefjeff-free --keys-file /etc/chefjeff-free/model-keys.json --site-credentials /etc/chefjeff-free/sites.json --models-verifiedEXTRA
Environment=PYTHONDONTWRITEBYTECODE=1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/chefjeff-free
InaccessiblePaths=-/var/lib/chefjeff-data -/var/lib/chefjeff -/var/lib/chefjeff-admin -/etc/chefjeff-admin -/etc/letsencrypt
MemoryMax=256M
TasksMax=48

[Install]
WantedBy=multi-user.target
'''.replace('RELEASE', str(path)).replace('EXTRA', EXTRA_FLAGS if extra_models else '')
