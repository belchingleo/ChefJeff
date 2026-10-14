#!/usr/bin/env bash
# Complete the reviewed Hetzner pilot's firewall and HTTPS maintenance setup.
set -euo pipefail

if (( EUID != 0 )); then
    printf 'Run this on the deployment server as root.\n' >&2
    exit 1
fi
for chefjeff_command in nft nginx certbot systemctl systemd-analyze; do
    command -v "$chefjeff_command" >/dev/null
done
chefjeff_nft=$(command -v nft)
chefjeff_nginx=$(command -v nginx)
chefjeff_systemctl=$(command -v systemctl)

# This drop-in is specific to the existing reviewed VPN firewall service/table.
systemctl is-active --quiet personal-vpn-firewall.service
systemctl is-enabled --quiet personal-vpn-firewall.service
nft --check add rule inet personal_vpn_filter input tcp dport '{ 80, 443 }' accept
nginx -t

chefjeff_temp=$(mktemp -d /tmp/chefjeff-finalize.XXXXXX)
trap 'rm -rf "$chefjeff_temp"' EXIT
cat > "$chefjeff_temp/firewall.conf" <<EOF
[Service]
ExecStartPost=$chefjeff_nft add rule inet personal_vpn_filter input tcp dport { 80, 443 } accept
ExecReload=$chefjeff_nft add rule inet personal_vpn_filter input tcp dport { 80, 443 } accept
EOF
cat > "$chefjeff_temp/renew-nginx.sh" <<EOF
#!/bin/sh
set -eu
case "\${RENEWED_LINEAGE:-}" in
    /etc/letsencrypt/live/chefjeff.belchingleo.online) ;;
    *) exit 0 ;;
esac
$chefjeff_nginx -t
$chefjeff_systemctl reload nginx
EOF

# Back up only files owned by this deployment, if this helper ran previously.
for chefjeff_file in /etc/systemd/system/personal-vpn-firewall.service.d/chefjeff-web.conf \
                     /etc/letsencrypt/renewal-hooks/deploy/chefjeff-nginx; do
    if [[ -e "$chefjeff_file" || -L "$chefjeff_file" ]]; then
        cp --no-dereference --update=none "$chefjeff_file" "$chefjeff_file.before-finalize"
    fi
done
install -d /etc/systemd/system/personal-vpn-firewall.service.d
install -m 0644 "$chefjeff_temp/firewall.conf" /etc/systemd/system/personal-vpn-firewall.service.d/chefjeff-web.conf
install -d /etc/letsencrypt/renewal-hooks/deploy
install -m 0750 "$chefjeff_temp/renew-nginx.sh" /etc/letsencrypt/renewal-hooks/deploy/chefjeff-nginx
systemd-analyze verify personal-vpn-firewall.service
systemctl daemon-reload

# Apply only the web-port addition, without restarting the existing VPN service.
if ! nft -n list chain inet personal_vpn_filter input | grep -Eq 'tcp dport \{ 80, 443 \} accept'; then
    nft add rule inet personal_vpn_filter input tcp dport '{ 80, 443 }' accept
fi
systemctl enable --now certbot.timer
printf 'Web-port persistence and certificate reload hook installed. Testing renewal...\n'
certbot renew --cert-name chefjeff.belchingleo.online --dry-run --run-deploy-hooks
printf 'ChefJeff maintenance setup and renewal check completed.\n'
