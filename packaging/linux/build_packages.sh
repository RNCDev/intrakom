#!/bin/bash
# Produce .deb and .rpm for both receiver and hub using fpm.
# Prereqs: ruby + `gem install fpm`; PyInstaller outputs in dist/.
# Usage: build_packages.sh <version>
set -euo pipefail
VERSION="${1:?version required}"

command -v fpm >/dev/null || { echo "fpm not found — install with: gem install fpm"; exit 1; }

# Map uname -m to fpm/deb/rpm arch names
case "$(uname -m)" in
  x86_64)  DEB_ARCH=amd64;  RPM_ARCH=x86_64 ;;
  aarch64) DEB_ARCH=arm64;  RPM_ARCH=aarch64 ;;
  armv7l)  DEB_ARCH=armhf;  RPM_ARCH=armhfp ;;
  *)       DEB_ARCH=$(uname -m); RPM_ARCH=$(uname -m) ;;
esac

# Input binaries from PyInstaller (onefile mode on linux)
RECV_BIN="dist/Intrakom Receiver"
HUB_BIN="dist/intrakom-hub"
[ -f "$RECV_BIN" ] || { echo "Missing $RECV_BIN"; exit 1; }
[ -f "$HUB_BIN" ]  || { echo "Missing $HUB_BIN";  exit 1; }

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mk_pkg () {  # mk_pkg <type> <target>
  local type="$1" target="$2"
  local name="intrakom-${target,,}"
  local root="$STAGE/$name"
  mkdir -p "$root/usr/bin" "$root/lib/systemd"
  if [ "$target" = "Receiver" ]; then
    cp "$RECV_BIN" "$root/usr/bin/intrakom-receiver"
    mkdir -p "$root/lib/systemd/user"
    cp packaging/linux/intrakom-receiver.service "$root/lib/systemd/user/"
  else
    cp "$HUB_BIN" "$root/usr/bin/intrakom-hub"
    mkdir -p "$root/lib/systemd/system"
    cp packaging/linux/intrakom-hub.service "$root/lib/systemd/system/"
  fi
  chmod +x "$root"/usr/bin/*

  local arch after_install_flag=""
  [ "$type" = "rpm" ] && arch="$RPM_ARCH" || arch="$DEB_ARCH"

  # Hub runs as a dedicated system user; create it on install
  if [ "$target" = "Hub" ]; then
    local postinst="$STAGE/postinst-hub"
    cat > "$postinst" <<'POSTINST'
#!/bin/sh
if ! id -u intrakom >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin intrakom
fi
systemctl daemon-reload
systemctl enable intrakom-hub
systemctl restart intrakom-hub
POSTINST
    chmod +x "$postinst"
    after_install_flag="--after-install $postinst"
  fi

  fpm -s dir -t "$type" \
      -n "$name" -v "$VERSION" \
      --architecture "$arch" \
      --description "Intrakom ${target}" \
      --url "https://github.com/RNCDev/intrakom" \
      --license "MIT" \
      $after_install_flag \
      -C "$root" \
      -p "dist/${name}_${VERSION}_${arch}.${type}" \
      usr lib
}

mk_pkg deb Receiver
mk_pkg rpm Receiver
mk_pkg deb Hub
mk_pkg rpm Hub

echo "Done: dist/intrakom-*_${VERSION}_*"
