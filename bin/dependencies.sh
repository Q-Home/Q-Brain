#!/bin/bash
# Root-only Debian bootstrap. Called before the Python-based installation hooks.
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l
trap 'echo "<ERROR> Dependency installation failed at line $LINENO. Check the preceding apt/Docker message and retry installation."' ERR

fail() { echo "<ERROR> $*"; exit 2; }
installed() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -qx 'install ok installed'; }
apt_install() {
    apt-get -o DPkg::Lock::Timeout=300 -o Acquire::Retries=3 install -y --no-remove --no-upgrade "$@"
}
candidate() { apt-cache policy "$1" | awk '/Candidate:/ {print $2; exit}'; }
install_first_available() {
    local package version
    for package in "$@"; do
        version="$(candidate "$package")"
        if [ -n "$version" ] && [ "$version" != '(none)' ]; then
            apt_install "$package"
            return
        fi
    done
    fail "No compatible package found for: $*. Existing Docker has not been replaced."
}

ensure_repository() {
    local aptroot="$1" suite="$2" arch="$3" keytemp
    if grep -rqs 'https://download.docker.com/linux/debian' "$aptroot/apt/sources.list" "$aptroot/apt/sources.list.d" 2>/dev/null; then
        return
    fi
    install -d -m 0755 "$aptroot/apt/keyrings" "$aptroot/apt/sources.list.d"
    keytemp="$(mktemp)"
    if ! curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
        --retry 3 --connect-timeout 20 --max-time 120 \
        https://download.docker.com/linux/debian/gpg -o "$keytemp"; then
        rm -f "$keytemp"
        fail 'Could not download the official Docker signing key.'
    fi
    grep -q 'BEGIN PGP PUBLIC KEY BLOCK' "$keytemp" || { rm -f "$keytemp"; fail 'Invalid Docker signing key response.'; }
    install -m 0644 "$keytemp" "$aptroot/apt/keyrings/qbrain-docker.asc"
    rm -f "$keytemp"
    printf 'Types: deb\nURIs: https://download.docker.com/linux/debian\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: %s/apt/keyrings/qbrain-docker.asc\n' \
        "$suite" "$arch" "$aptroot" > "$aptroot/apt/sources.list.d/qbrain-docker.sources"
    chmod 0644 "$aptroot/apt/sources.list.d/qbrain-docker.sources"
}

main() {
    [ "$(id -u)" = 0 ] || fail 'Dependency installation must run as root.'
    [ -d /run/systemd/system ] || fail 'A native LoxBerry host with systemd is required.'
    [ -f /etc/debian_version ] || fail 'Automatic installation supports Debian-based LoxBerry hosts only.'
    local arch suite major missing=() package
    arch="$(dpkg --print-architecture)"
    case "$arch" in arm64|amd64) ;; *) fail "Unsupported architecture: $arch" ;; esac
    major="$(cut -d. -f1 /etc/debian_version)"
    case "$major" in 11) suite=bullseye ;; 12) suite=bookworm ;; 13) suite=trixie ;;
        *) fail 'Supported Debian releases are 11, 12 and 13; refusing to guess the Docker repository.' ;; esac
    echo "<INFO> Preparing dependencies for Debian $major ($arch). Internet access is required."
    for package in ca-certificates curl python3 sudo php-cli php-curl php-xml; do
        installed "$package" || missing+=("$package")
    done
    if [ "${#missing[@]}" -gt 0 ] || ! /usr/bin/docker compose version >/dev/null 2>&1 || ! /usr/bin/docker buildx version >/dev/null 2>&1; then
        apt-get -o DPkg::Lock::Timeout=300 -o Acquire::Retries=3 update
    fi
    if [ "${#missing[@]}" -gt 0 ]; then apt_install "${missing[@]}"; fi

    if [ ! -x /usr/bin/docker ]; then
        # Do not silently remove another runtime to make room for Docker CE.
        for package in docker.io podman-docker containerd runc; do
            installed "$package" && fail "Existing $package conflicts with a fresh Docker CE install. Resolve the runtime choice before retrying."
        done
        ensure_repository /etc "$suite" "$arch"
        apt-get -o DPkg::Lock::Timeout=300 -o Acquire::Retries=3 update
        apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    else
        echo '<INFO> Existing Docker detected; keeping its engine and data.'
        if ! /usr/bin/docker compose version >/dev/null 2>&1; then
            if installed docker-ce; then
                install_first_available docker-compose-plugin
            elif installed docker.io; then
                install_first_available docker-compose-v2 docker-compose
            else
                fail 'Existing unmanaged Docker has no Compose plugin. Install its matching Compose plugin first.'
            fi
        fi
        if ! /usr/bin/docker buildx version >/dev/null 2>&1; then
            if installed docker-ce; then install_first_available docker-buildx-plugin
            elif installed docker.io; then install_first_available docker-buildx
            else fail 'Existing unmanaged Docker has no Buildx plugin. Install its matching Buildx plugin first.'; fi
        fi
    fi
    /usr/bin/python3 -c 'import sys; assert sys.version_info >= (3, 9)'
    /usr/bin/php -v >/dev/null
    /usr/sbin/visudo -V >/dev/null
    /usr/bin/docker compose version
    /usr/bin/docker buildx version
    # Start only if inactive: never restart a running engine with other containers.
    systemctl enable docker.service
    if ! systemctl is-active --quiet docker.service; then systemctl start docker.service; fi
    local attempt
    for attempt in {1..30}; do
        if /usr/bin/docker info --format '{{.ServerVersion}}' >/dev/null 2>&1; then
            echo '<OK> Host dependencies, Docker Engine, Compose and Buildx are ready.'
            return
        fi
        sleep 2
    done
    fail 'Docker was installed but its daemon did not become ready. Inspect journalctl -u docker.'
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
