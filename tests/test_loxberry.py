import configparser
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


control = load_module('qbrain_control', ROOT / 'bin/control.py')
builder = load_module('qbrain_builder', ROOT / 'scripts/build_loxberry.py')


def settings():
    return {**control.DEFAULTS, 'demo_mode': True, 'loxberry_sdk': False, 'mcp_token': 'test-local-token', 'revision': 1}


def test_loxberry_archive(tmp_path):
    package = builder.build(tmp_path / 'plugin.zip')
    with zipfile.ZipFile(package) as z:
        names = set(z.namelist())
        assert {'plugin.cfg', 'preinstall.sh', 'preroot.sh', 'postroot.sh', 'daemon/daemon',
                'uninstall/uninstall', 'webfrontend/htmlauth/index.php',
                'templates/index.php', 'templates/help/help.html', 'icons/icon.svg',
                'bin/healthcheck', 'bin/install.py', 'bin/control.py', 'bin/dependencies.sh',
                'bin/service/Dockerfile', 'bin/service/qbox/server.py'} <= names
        assert not any('/.env' in name or name.endswith('.env') or '__pycache__' in name for name in names)
        assert not any(name.startswith('webfrontend/html/') for name in names)
        for name in names:
            if not name.startswith('webfrontend/htmlauth/chat/'):
                assert b'\r\n' not in z.read(name)
        for name in ('preinstall.sh', 'preroot.sh', 'postroot.sh', 'bin/control.py', 'bin/healthcheck', 'daemon/daemon'):
            assert ((z.getinfo(name).external_attr >> 16) & 0o777) == 0o755
        metadata = configparser.ConfigParser()
        metadata.read_string(z.read('plugin.cfg').decode())
        assert metadata['PLUGIN']['NAME'] == 'qbrain'
        assert metadata['AUTHOR']['NAME'] and '@' in metadata['AUTHOR']['EMAIL']
        assert metadata['SYSTEM']['LB_MINIMUM'] == '4.0.0'
        assert 'webfrontend/htmlauth/chat/index.html' in names
        with zipfile.ZipFile(ROOT / 'vendor/hollama-ui.zip') as frontend:
            for entry in frontend.namelist():
                assert z.read('webfrontend/htmlauth/chat/' + entry) == frontend.read(entry)
        assert z.read('bin/service/qbox/server.py') == (ROOT / 'qbox/server.py').read_bytes()


@pytest.mark.parametrize('payload', [
    {'observe_only': False}, {'enable_ev_write': True}, {'docker_host': 'evil'},
    {'mcp_port': True}, {'mcp_port': 22}, {'mcp_port': 65536},
    {'loxone_url': 'https://user:password@miniserver'},
    {'loxone_url': 'file:///etc/passwd'}, {'loxone_url': 'https://miniserver/command'},
    {'loxone_grid_power': '../On'}, {'loxone_username': 'user\nMCP_TOKEN=x'},
    {'ollama_model': '--help'}, {'ollama_model': 'model;touch /tmp/a'},
    {'demo_mode': False}, {'ev_max_power_w': 99999}, {'reasoning_interval_seconds': 0},
])
def test_settings_reject_unsafe_or_invalid_inputs(payload):
    with pytest.raises(control.ControlError):
        control.validate(payload, settings())


def test_password_is_preserved_and_redacted():
    old = {**settings(), 'loxone_password': "secret$'\\value"}
    merged = control.validate({'loxone_password': '', 'mcp_port': 18081}, old)
    assert merged['loxone_password'] == old['loxone_password']
    public = control.public_config({**old, **merged})
    assert public['loxone_password_set'] is True
    assert 'loxone_password' not in public and 'mcp_token' not in public


def test_compose_forces_observe_only_and_escapes_dollars(tmp_path):
    config = {**settings(), 'loxone_password': '${EVIL_VAR}', 'observe_only': False}
    compose = control.compose_document(config, tmp_path, 'qbrain01')
    qbox = compose['services']['qbox']
    assert qbox['environment']['OBSERVE_ONLY'] == 'true'
    assert qbox['environment']['ENABLE_EV_WRITE'] == 'false'
    assert qbox['environment']['LOXONE_PASSWORD'] == '$${EVIL_VAR}'
    assert qbox['ports'] == ['127.0.0.1:18080:8080']
    assert qbox['build'] == str(tmp_path / 'service')
    for service in compose['services'].values():
        assert not service.get('privileged', False)
        assert not any('docker.sock' in mount for mount in service.get('volumes', []))


def test_real_mode_requires_explicit_http_permission():
    real = {**settings(), 'demo_mode': False, 'loxone_url': 'http://miniserver',
            'loxone_username': 'user', 'loxone_password': 'secret'}
    real.update({'loxone_' + k: k for k in control.MAPPINGS})
    with pytest.raises(control.ControlError):
        control.validate({}, real)
    assert control.validate({'loxone_allow_http': True}, real)['demo_mode'] is False


@pytest.fixture
def controller(tmp_path):
    c = control.Controller.__new__(control.Controller)
    c.state = tmp_path
    c.runtime = tmp_path / 'runtime'
    c.folder = 'qbrain01'
    c.settings_file = tmp_path / 'settings.json'
    c.compose_file = tmp_path / 'compose.json'
    c.job_file = tmp_path / 'job.json'
    c.log_file = tmp_path / 'operation.log'
    control.atomic_json(c.settings_file, settings())
    @contextmanager
    def lock():
        yield 123
    c.lock = lock
    return c


def test_initialize_preserves_existing_configuration(controller):
    before = controller.settings_file.read_bytes()
    controller.dispatch('initialize')
    assert controller.settings_file.read_bytes() == before


def test_boot_only_resumes_requested_running_state(controller):
    controller.schedule = Mock(return_value={'accepted': True})
    assert controller.dispatch('boot') == {'started': False}
    controller.schedule.assert_not_called()
    control.atomic_json(controller.state / 'desired.json', {'running': True})
    assert controller.dispatch('boot')['accepted'] is True
    controller.schedule.assert_called_once_with('start')


def test_operation_error_does_not_mark_applied(controller, monkeypatch):
    controller.run = Mock(side_effect=RuntimeError('failed'))
    monkeypatch.setattr(control.os, 'fstat', lambda fd: None)
    monkeypatch.setattr(control.os, 'close', lambda fd: None)
    controller.worker('start', 123)
    assert control.read_json(controller.job_file)['status'] == 'failed'
    assert not (controller.state / 'applied.json').exists()


def test_stop_retains_volumes(controller, monkeypatch):
    controller.compose_file.write_text('{}')
    controller.run = Mock()
    monkeypatch.setattr(control.os, 'fstat', lambda fd: None)
    monkeypatch.setattr(control.os, 'close', lambda fd: None)
    controller.worker('stop', 123)
    controller.run.assert_called_once_with('down', '--remove-orphans', timeout=180)


def test_management_logs_redact_secrets(controller):
    data = {**settings(), 'loxone_password': 'password-secret', 'loxone_username': 'private-user'}
    control.atomic_json(controller.settings_file, data)
    controller.log_file.write_text('password-secret private-user test-local-token')
    assert controller.logs()['text'] == '[redacted] [redacted] [redacted]'


def test_docker_command_ignores_caller_environment(controller, monkeypatch):
    monkeypatch.setenv('DOCKER_HOST', 'tcp://untrusted:2375')
    monkeypatch.setenv('COMPOSE_FILE', '/tmp/evil.yml')
    assert 'DOCKER_HOST' not in controller.process_env()
    assert 'COMPOSE_FILE' not in controller.process_env()
    assert controller.command('down')[:4] == ['/usr/bin/docker', 'compose', '--project-name', 'qbrain-qbrain01']


def test_saving_configuration_requires_no_active_job(controller, monkeypatch):
    import io
    monkeypatch.setattr(control.sys, 'stdin', io.StringIO('{"mcp_port":18081}'))
    @contextmanager
    def busy():
        raise control.ControlError('busy')
        yield
    controller.lock = busy
    with pytest.raises(control.ControlError):
        controller.dispatch('save')
    assert controller.settings()['mcp_port'] == 18080


@pytest.mark.skipif(__import__('os').name == 'nt', reason='Linux flock integration')
def test_linux_flock_blocks_overlapping_operations(controller):
    # Real advisory lock, tested by CI on the deployment operating system.
    controller.lock = control.Controller.lock.__get__(controller)
    with controller.lock():
        with pytest.raises(control.ControlError):
            with controller.lock():
                pass


def test_sdk_compose_contains_no_loxone_credentials(tmp_path):
    config = {**settings(), 'loxberry_sdk': True, 'demo_mode': False,
              'loxone_username': 'private-user', 'loxone_password': 'private-password'}
    compose = control.compose_document(config, tmp_path, 'qbrain01')
    assert 'private-user' not in json.dumps(compose) and 'private-password' not in json.dumps(compose)
    mount = compose['services']['qbox']['volumes'][1]
    assert mount == {'type': 'bind', 'source': '/var/lib/qbrain/qbrain01/telemetry', 'target': '/telemetry', 'read_only': True}
    assert 'config/system' not in json.dumps(compose)
    assert control.validate({'demo_mode': False, 'loxberry_sdk': True}, settings())['loxberry_sdk']


def test_sdk_upgrade_migrates_without_credentials_in_public_config(controller):
    old = settings(); old.pop('loxberry_sdk'); old.pop('miniserver_id')
    old['loxone_username'] = 'private-user'
    control.atomic_json(controller.settings_file, old)
    migrated = controller.settings()
    assert migrated['loxberry_sdk'] and not migrated['demo_mode']
    assert migrated['revision'] == old['revision'] + 1
    assert 'private-user' not in json.dumps(control.public_config(migrated))
    assert controller.settings()['revision'] == migrated['revision']


def test_sdk_start_sets_up_collector_and_model(controller, monkeypatch):
    control.atomic_json(controller.settings_file, {**settings(), 'demo_mode': False, 'loxberry_sdk': True})
    controller.start_collector = Mock()
    controller.ensure_model = Mock()
    controller.run = Mock()
    monkeypatch.setattr(control.os, 'fstat', lambda fd: None)
    monkeypatch.setattr(control.os, 'close', lambda fd: None)
    controller.worker('start', 123)
    controller.start_collector.assert_called_once()
    controller.ensure_model.assert_called_once()
    assert control.read_json(controller.job_file)['status'] == 'completed'


def test_existing_model_does_not_download(controller, monkeypatch):
    monkeypatch.setattr(control.subprocess, 'run', Mock())
    controller.run = Mock()
    controller.ensure_model()
    controller.run.assert_called_once_with('exec', '-T', 'ollama', 'ollama', 'show', 'qwen3:4b', timeout=30)


def test_missing_model_downloads(controller, monkeypatch):
    monkeypatch.setattr(control.subprocess, 'run', Mock())
    controller.run = Mock(side_effect=[control.subprocess.CalledProcessError(1, ['show']), None])
    controller.ensure_model()
    assert controller.run.call_args.args == ('exec', '-T', 'ollama', 'ollama', 'pull', 'qwen3:4b')


def test_release_feed_matches_installable_archive():
    from urllib.parse import urlsplit
    metadata = configparser.ConfigParser()
    metadata.read(ROOT / 'plugin.cfg', encoding='utf-8')
    assert metadata.getboolean('AUTOUPDATE', 'AUTOMATIC_UPDATES')
    assert metadata['AUTOUPDATE']['RELEASECFG'] == 'https://raw.githubusercontent.com/Q-Home/Q-Brain/main/release.cfg'
    feed = configparser.ConfigParser()
    feed.read(ROOT / 'release.cfg', encoding='utf-8')
    release = feed['AUTOUPDATE']
    assert release['VERSION'] == metadata['PLUGIN']['VERSION']
    url = urlsplit(release['ARCHIVEURL'])
    assert url.scheme == 'https' and url.netloc == 'raw.githubusercontent.com'
    assert url.path == '/Q-Home/Q-Brain/main/packages/qbrain-loxberry-' + release['VERSION'] + '.zip'
    with zipfile.ZipFile(ROOT / 'packages' / url.path.split('/')[-1]) as archive:
        bundled = configparser.ConfigParser()
        bundled.read_string(archive.read('plugin.cfg').decode())
        assert bundled['PLUGIN'] == metadata['PLUGIN']
        assert bundled['AUTHOR'] == metadata['AUTHOR']
        assert bundled['AUTOUPDATE'] == metadata['AUTOUPDATE']
        assert 'bin/service/qbox/server.py' in archive.namelist()
    assert release['INFOURL'] == 'https://github.com/Q-Home/Q-Brain/blob/main/docs/CHANGELOG.md'


def test_local_image_is_built_before_start_and_never_pulled(controller, monkeypatch):
    compose = control.compose_document(settings(), controller.runtime, controller.folder)
    assert compose['services']['qbox']['pull_policy'] == 'never'
    assert compose['services']['agent']['pull_policy'] == 'never'
    assert compose['services']['ollama'].get('pull_policy') != 'never'
    controller.run = Mock(); controller.ensure_model = Mock()
    monkeypatch.setattr(control.os, 'fstat', lambda fd: None)
    monkeypatch.setattr(control.os, 'close', lambda fd: None)
    controller.worker('start', 123)
    assert controller.run.call_args_list[0].args == ('build', 'qbox')
    assert controller.run.call_args_list[1].args == ('up', '-d', '--no-build', 'qbox', 'ollama')


def test_sdk_failure_is_preserved_without_stderr_or_raw_error(controller, monkeypatch):
    controller.runtime.mkdir()
    control.atomic_json(controller.runtime / 'installation.json', {'home': '/opt/loxberry'})
    monkeypatch.setattr(control.subprocess, 'run', Mock(return_value=Mock(returncode=1,
        stdout=b'{"error":"secret-password", "error_code":"authentication"}', stderr=b'secret-password')))
    with pytest.raises(control.ControlError, match='401/403') as failure:
        controller.sdk('collect', '1')
    assert 'secret-password' not in str(failure.value)
