#!/usr/bin/env python3
"""Render regional Nginx/systemd files for review; never install or restart them."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def domain_name(value):
    if (not isinstance(value, str) or len(value) > 253 or '.' not in value
            or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in value.split('.'))):
        raise ValueError('Use a lowercase DNS hostname')
    return value


def game_nginx(domain, aliases=(), legacy=()):
    domain_name(domain)
    names = [domain, *aliases, *legacy]
    if len(names) > 12 or len(set(names)) != len(names):
        raise ValueError('Duplicate or excessive hostnames')
    for name in names:
        domain_name(name)
    template = (ROOT/'deploy/nginx-https.conf').read_text()
    zones = template[:template.index('server {')]
    marker = 'server {\n    listen 443 ssl http2;\n    server_name chefjeff.online;'
    main = template[template.index(marker):].replace('chefjeff.online', domain)
    http = ('server {\n    listen 80;\n    server_name '+ ' '.join(names)+';\n'
            '    access_log off;\n    error_log /dev/null;\n'
            '    location /.well-known/acme-challenge/ { root /var/www/chefjeff-acme; }\n'
            '    location / { return 301 https://'+domain+'$request_uri; }\n}\n')
    redirects = ''
    for alias in (*aliases, *legacy):
        lineage = alias if alias in legacy else domain
        redirects += ('server {\n    listen 443 ssl http2;\n    server_name '+alias+';\n'
            '    ssl_certificate /etc/letsencrypt/live/'+lineage+'/fullchain.pem;\n'
            '    ssl_certificate_key /etc/letsencrypt/live/'+lineage+'/privkey.pem;\n'
            '    ssl_protocols TLSv1.2 TLSv1.3;\n    access_log off;\n    error_log /dev/null;\n'
            '    return 301 https://'+domain+'$request_uri;\n}\n')
    return zones + http + redirects + main


def game_unit(domain):
    domain_name(domain)
    template = (ROOT/'deploy/chefjeff.service').read_text()
    return template.replace('--origin https://chefjeff.online', '--origin https://'+domain).replace(
        '--data-dir /var/lib/chefjeff', '--data-dir /var/lib/chefjeff --shared-config /etc/chefjeff/shared-client.json')


def data_nginx(domain, peer_ip):
    import ipaddress
    domain_name(domain)
    peer_ip = str(ipaddress.ip_address(peer_ip))
    return '''server {
    listen 80;
    server_name DOMAIN;
    access_log off;
    error_log /dev/null;
    location /.well-known/acme-challenge/ { root /var/www/chefjeff-acme; }
    location / { return 503; }
}
server {
    listen 443 ssl http2;
    server_name DOMAIN;
    ssl_certificate /etc/letsencrypt/live/DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    access_log off;
    error_log /dev/null;
    client_max_body_size 14m;
    client_body_buffer_size 14m;
    client_body_timeout 10s;
    location /v1/ {
        allow PEER;
        allow 127.0.0.1;
        deny all;
        proxy_http_version 1.1;
        proxy_request_buffering off;
        proxy_buffering off;
        proxy_max_temp_file_size 0;
        proxy_connect_timeout 3s;
        proxy_read_timeout 10s;
        proxy_set_header Host DOMAIN;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header X-ChefJeff-Site $http_x_chefjeff_site;
        proxy_set_header Cookie "";
        proxy_pass http://127.0.0.1:8790;
    }
    location / { return 404; }
}
'''.replace('DOMAIN', domain).replace('PEER', peer_ip)


def renewal_hook(domains):
    paths = '|'.join('/etc/letsencrypt/live/'+domain_name(domain) for domain in domains)
    return ('#!/bin/sh\nset -eu\ncase "${RENEWED_LINEAGE:-}" in\n    '+paths+
            ') ;;\n    *) exit 0 ;;\nesac\n/usr/sbin/nginx -t\n/bin/systemctl reload nginx\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', required=True)
    parser.add_argument('--alias', action='append', default=[])
    parser.add_argument('--legacy-redirect', action='append', default=[])
    parser.add_argument('--data-domain')
    parser.add_argument('--peer-ip')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if bool(args.data_domain) != bool(args.peer_ip):
        parser.error('data-domain and peer-ip must be supplied together')
    files = {'chefjeff.nginx.conf': game_nginx(args.domain, args.alias, args.legacy_redirect),
             'chefjeff.service': game_unit(args.domain)}
    if args.data_domain:
        files['chefjeff-data.nginx.conf'] = data_nginx(args.data_domain, args.peer_ip)
        files['chefjeff-data.service'] = (ROOT/'deploy/chefjeff-data.service').read_text()
    files['chefjeff-renew-hook'] = renewal_hook([args.domain, *args.legacy_redirect, *([args.data_domain] if args.data_domain else [])])
    args.output_dir.mkdir(parents=True, exist_ok=False)
    for name, content in files.items():
        (args.output_dir/name).write_text(content)
    print('Review files rendered in '+str(args.output_dir))


if __name__ == '__main__':
    main()
