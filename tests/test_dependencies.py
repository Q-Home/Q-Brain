"""Run the real Bash bootstrap with simulated host/package commands; never install locally."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get('BASH_BINARY') or shutil.which('bash')
pytestmark = pytest.mark.skipif(not BASH, reason='Bash not available')

HARNESS = r'''
source "$1"
scenario="$2"
log="$3"
docker_ready=0
compose_ready=0
function id { echo 0; }
function dpkg { echo arm64; }
function cut { echo "${TEST_DEBIAN:-12}"; }
function [ {
    if [[ "${1-}" == '!' ]]; then
        shift
        if [ "$@"; then return 1; else return 0; fi
    fi
    case "${1-}:${2-}" in
        -d:/run/systemd/system|-f:/etc/debian_version) return 0 ;;
        -x:/usr/bin/docker) [[ "$scenario" == existing || "$scenario" == missing-compose || "$docker_ready" == 1 ]] ;;
        *) builtin [ "$@" ;;
    esac
}
function installed {
    case "$1" in
        docker-ce) [[ "$scenario" == existing || "$scenario" == missing-compose ]] ;;
        docker.io|podman-docker|runc) return 1 ;;
        containerd) [[ "$scenario" == conflict ]] ;;
        *) [[ "$scenario" != fresh ]] ;;
    esac
}
function apt-get {
    echo "apt-get $*" >> "$log"
    if [[ "$scenario" == apt-failure ]]; then return 42; fi
    if [[ "$*" == *' docker-ce '* ]]; then docker_ready=1; fi
    if [[ "$*" == *'docker-compose-plugin'* ]]; then compose_ready=1; fi
}
function apt-cache { echo '  Candidate: 2.40.0'; }
function ensure_repository { echo "repository $*" >> "$log"; }
function /usr/bin/docker {
    case "$1" in
        compose) [[ "$scenario" == existing || "$compose_ready" == 1 ]] ;;
        buildx) [[ "$scenario" == existing || "$scenario" == missing-compose || "$docker_ready" == 1 ]] ;;
        info) return 0 ;;
        *) return 1 ;;
    esac
}
function /usr/bin/python3 { return 0; }
function /usr/bin/php { return 0; }
function /usr/sbin/visudo { return 0; }
function systemctl {
    echo "systemctl $*" >> "$log"
    if [[ "$1" == is-active && "$scenario" != existing ]]; then return 1; fi
}
main
'''


def run_host(tmp_path, scenario, **env):
    harness = tmp_path / 'simulate.sh'
    harness.write_text(HARNESS, encoding='utf-8', newline='\n')
    log = tmp_path / 'commands.log'
    result = subprocess.run([BASH, str(harness), str(ROOT / 'bin/dependencies.sh'), scenario, str(log)],
                            capture_output=True, text=True, env={**os.environ, **env}, timeout=15)
    return result, log.read_text() if log.exists() else ''


def test_fresh_host_installs_dependencies(tmp_path):
    result, commands = run_host(tmp_path, 'fresh')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'ca-certificates curl python3 sudo php-cli' in commands
    assert 'docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin' in commands
    assert '--no-remove --no-upgrade' in commands
    assert 'systemctl start docker.service' in commands


def test_existing_docker_not_reinstalled_or_restarted(tmp_path):
    result, commands = run_host(tmp_path, 'existing')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'apt-get' not in commands
    assert 'systemctl start' not in commands and 'systemctl restart' not in commands


def test_missing_compose_added_without_engine_replacement(tmp_path):
    result, commands = run_host(tmp_path, 'missing-compose')
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'install -y --no-remove --no-upgrade docker-compose-plugin' in commands
    assert 'install -y --no-remove --no-upgrade docker-ce ' not in commands


def test_conflicting_runtime_is_not_removed(tmp_path):
    result, commands = run_host(tmp_path, 'conflict')
    assert result.returncode == 2
    assert 'conflicts' in result.stdout
    assert 'remove ' not in commands.replace('--no-remove ', '')


def test_apt_failure_aborts_installation(tmp_path):
    result, commands = run_host(tmp_path, 'apt-failure')
    assert result.returncode != 0
    assert '<ERROR>' in result.stdout
    assert 'systemctl' not in commands


def test_unsupported_debian_aborts_before_apt(tmp_path):
    result, commands = run_host(tmp_path, 'fresh', TEST_DEBIAN='99')
    assert result.returncode == 2
    assert commands == ''


@pytest.mark.skipif(os.name == 'nt', reason='POSIX install utility and file modes; exercised on Linux CI')
def test_signed_repository_creation_and_idempotence(tmp_path):
    harness = tmp_path / 'repo.sh'
    harness.write_text(r'''
source "$1"
function curl { printf '%s\n' '-----BEGIN PGP PUBLIC KEY BLOCK-----' > "${@: -1}"; }
ensure_repository "$2" bookworm arm64
function curl { return 99; }
ensure_repository "$2" bookworm arm64
''', newline='\n')
    result = subprocess.run([BASH, str(harness), str(ROOT / 'bin/dependencies.sh'), str(tmp_path / 'etc')], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    source = (tmp_path / 'etc/apt/sources.list.d/qbrain-docker.sources').read_text()
    assert 'Suites: bookworm' in source and 'Architectures: arm64' in source
    assert 'Signed-By:' in source and 'qbrain-docker.asc' in source
