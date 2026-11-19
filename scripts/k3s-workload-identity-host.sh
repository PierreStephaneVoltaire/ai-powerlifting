#!/bin/sh
set -eu

case "$ISSUER" in https://[a-zA-Z0-9.-]* ) ;; *) exit 1 ;; esac
case "$PREVIOUS_ISSUER" in https://[a-zA-Z0-9.-]* ) ;; *) exit 1 ;; esac
case "$ISSUER$PREVIOUS_ISSUER" in *[!a-zA-Z0-9./:-]*) exit 1 ;; esac
[ "$ISSUER" != "$PREVIOUS_ISSUER" ] || exit 1
[ -x /host/usr/bin/systemd-run ] && [ -x /host/usr/bin/systemctl ] || exit 1
[ -f /host/etc/systemd/system/k3s.service ] || exit 1

config_dir=/host/etc/rancher/k3s/config.yaml.d
target="$config_dir/zzzz-nolift-workload-identity.yaml"
for file in /host/etc/rancher/k3s/config.yaml "$config_dir"/*.yaml /host/etc/systemd/system/k3s.service /host/etc/systemd/system/k3s.service.env /host/etc/default/k3s /host/etc/sysconfig/k3s; do
  [ -f "$file" ] || continue
  [ "$file" != "$target" ] || continue
  if grep -Eiq 'kube-apiserver-arg|service-account-issuer|service-account-jwks-uri|api-audiences|K3S_CONFIG_FILE|(^|[[:space:]])--config([=[:space:]]|$)' "$file"; then
    printf '%s\n' 'Conflicting k3s API server configuration requires review' >&2
    exit 1
  fi
done
mkdir -p "$config_dir"
temp="$config_dir/.nolift-workload-identity.$$"
trap 'rm -f "$temp"' EXIT HUP INT TERM
cat > "$temp" <<CONFIG
kube-apiserver-arg+:
  - service-account-issuer=$ISSUER
  - service-account-issuer=$PREVIOUS_ISSUER
  - service-account-jwks-uri=$ISSUER/openid/v1/jwks
CONFIG
chmod 600 "$temp"
mv "$temp" "$target"
chroot /host /usr/bin/systemd-run --on-active=15s /usr/bin/systemctl restart k3s
