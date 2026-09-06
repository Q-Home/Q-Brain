#!/usr/bin/python3 -I
"""Fixed-operation root controller for the LoxBerry UI; standard library only.

Runtime code lives in /usr/local/lib, settings in /var/lib. Neither is writable
by the web user. All Docker arguments and mounts are generated here, never supplied
by the browser. The LoxBerry edition always operates in observe-only mode.
"""
import contextlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

DEFAULTS = {
    'loxberry_sdk': True, 'miniserver_id': '',
    'demo_mode': False, 'loxone_url': 'https://miniserver.local',
    'loxone_username': '', 'loxone_password': '', 'loxone_allow_http': False,
    'loxone_grid_power': '', 'loxone_pv_power': '', 'loxone_battery_soc': '',
    'loxone_battery_power': '', 'loxone_ev_power': '',
    'ollama_model': 'qwen3:4b', 'mcp_port': 18080,
    'reasoning_interval_seconds': 300, 'ev_max_power_w': 11000,
}
MAPPINGS = ('grid_power', 'pv_power', 'battery_soc', 'battery_power', 'ev_power')
ACTIONS = ('config', 'save', 'status', 'start', 'stop', 'pull', 'logs', 'boot',
           'initialize', 'prepare_upgrade', 'uninstall', '_worker', '_collect')


class ControlError(Exception):
    pass


def validate(payload, current):
    if not isinstance(payload, dict) or set(payload) - set(DEFAULTS):
        raise ControlError('Unknown configuration fields')
    merged = {**DEFAULTS, **{k: v for k, v in current.items() if k in DEFAULTS}, **payload}
    if payload.get('loxone_password') == '':
        merged['loxone_password'] = current.get('loxone_password', '')
    for key, default in DEFAULTS.items():
        value = merged[key]
        if type(value) is not type(default):
            raise ControlError('Invalid field type: ' + key)
        if isinstance(value, str) and (len(value) > 512 or any(ord(ch) < 32 for ch in value)):
            raise ControlError('Invalid text in field: ' + key)
    for key in MAPPINGS:
        value = merged['loxone_' + key]
        if value and not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
            raise ControlError('Invalid Loxone input/output mapping')
    try:
        url = urlsplit(merged['loxone_url'])
        valid = (url.scheme in ('https', 'http') and url.hostname and not url.username
                 and not url.password and not url.query and not url.fragment
                 and url.path in ('', '/'))
        _ = url.port
    except ValueError:
        valid = False
    if not valid:
        raise ControlError('Enter a Loxone HTTP(S) origin without credentials or a path')
    if not re.fullmatch(r'[0-9]{0,5}', merged['miniserver_id']):
        raise ControlError('Invalid Miniserver selection')
    if not merged['demo_mode'] and not merged['loxberry_sdk']:
        if not merged['loxone_username'] or not merged['loxone_password'] or not all(merged['loxone_' + k] for k in MAPPINGS):
            raise ControlError('Real mode requires credentials and all five signal mappings')
        if url.scheme == 'http' and not merged['loxone_allow_http']:
            raise ControlError('Explicitly enable local HTTP or use HTTPS')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,127}', merged['ollama_model']):
        raise ControlError('Invalid Ollama model name')
    for key, low, high in [('mcp_port', 1024, 65535), ('reasoning_interval_seconds', 10, 86400), ('ev_max_power_w', 0, 22000)]:
        if not low <= merged[key] <= high:
            raise ControlError('Value outside allowed range: ' + key)
    return merged


def public_config(settings):
    return {**{k: settings[k] for k in DEFAULTS if k not in ('loxone_password', 'loxone_username')},
            'loxone_password_set': bool(settings.get('loxone_password')),
            'observe_only': True, 'revision': settings['revision']}


def compose_document(settings, runtime, folder):
    # Dollar escaping is required even in JSON: Compose interpolates string values.
    env = {k.upper(): str(settings[k]).lower() if isinstance(settings[k], bool) else str(settings[k])
           for k in DEFAULTS if k != 'mcp_port'}
    if settings.get('loxberry_sdk') and not settings['demo_mode']:
        env.update(LOXBERRY_SNAPSHOT_PATH='/telemetry/snapshot.json', LOXONE_USERNAME='', LOXONE_PASSWORD='')
    env.update(MCP_TOKEN=settings['mcp_token'], OBSERVE_ONLY='true', ENABLE_EV_WRITE='false',
               OLLAMA_URL='http://ollama:11434', HISTORY_PATH='/data/history.sqlite3')
    env = {k: v.replace('$', '$$') for k, v in env.items()}
    common = {'image': 'qbrain-' + folder + ':0.3.2', 'environment': env,
              'pull_policy': 'never', 'read_only': True, 'tmpfs': ['/tmp'], 'cap_drop': ['ALL'],
              'security_opt': ['no-new-privileges:true'], 'restart': 'unless-stopped',
              'logging': {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}}}
    return {'services': {
        'qbox': {**common, 'build': str(runtime / 'service'),
                 'ports': [f"127.0.0.1:{settings['mcp_port']}:8080"], 'volumes': ['history:/data'] + ([{'type': 'bind', 'source': '/var/lib/qbrain/' + folder + '/telemetry', 'target': '/telemetry', 'read_only': True}] if settings.get('loxberry_sdk') and not settings['demo_mode'] else [])},
        'agent': {**common, 'environment': {**env, 'MCP_URL': 'http://qbox:8080/mcp'},
                  'command': ['python', '-m', 'qbox.agent'], 'healthcheck': {'disable': True},
                  'depends_on': {'qbox': {'condition': 'service_healthy'}}},
        'ollama': {'image': 'ollama/ollama:0.11.10', 'volumes': ['ollama:/root/.ollama'],
                   'restart': 'unless-stopped', 'logging': common['logging']},
    }, 'volumes': {'history': {}, 'ollama': {}}}


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    # Directory is root-owned 0700; no user-supplied paths reach this function.
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


class Controller:
    def __init__(self, runtime):
        self.runtime = runtime.resolve()
        installation = read_json(self.runtime / 'installation.json')
        self.folder = installation['folder']
        if not re.fullmatch(r'[A-Za-z0-9_-]+', self.folder):
            raise ControlError('Invalid installed plugin folder')
        self.state = Path('/var/lib/qbrain') / self.folder
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.state, 0o700)
        self.settings_file = self.state / 'settings.json'
        self.compose_file = self.state / 'compose.json'
        self.job_file = self.state / 'job.json'
        self.log_file = self.state / 'operation.log'

    def settings(self):
        settings = read_json(self.settings_file)
        if settings is None:
            settings = {**DEFAULTS, 'mcp_token': secrets.token_hex(32), 'revision': 1}
            atomic_json(self.settings_file, settings)
        if 'loxberry_sdk' not in settings:
            settings = {**settings, 'loxberry_sdk': True, 'demo_mode': False, 'revision': settings['revision'] + 1}
            atomic_json(self.settings_file, settings)
        return {**DEFAULTS, **settings}

    @contextlib.contextmanager
    def lock(self):
        import fcntl
        with open(self.state / 'operation.lock', 'a') as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ControlError('An operation is already running; wait for it to finish') from None
            yield handle.fileno()

    def command(self, *args):
        return ['/usr/bin/docker', 'compose', '--project-name', 'qbrain-' + self.folder,
                '--project-directory', str(self.runtime / 'service'), '-f', str(self.compose_file), *args]

    def process_env(self):
        # Do not inherit DOCKER_HOST, COMPOSE_FILE, PATH or other caller overrides.
        return {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'HOME': '/root', 'LANG': 'C.UTF-8'}

    def sdk(self, action, selected=''):
        # SDK runs as the LoxBerry account, not root. Credentials never leave PHP.
        home = read_json(self.runtime / 'installation.json')['home']
        result = subprocess.run(['/usr/bin/sudo', '-u', 'loxberry', '/usr/bin/php',
                                 str(self.runtime / 'loxberry.php'), action, selected],
                                capture_output=True, timeout=30, env={**self.process_env(), 'LBHOMEDIR': home})
        if len(result.stdout) > 1048576:
            raise ControlError('SDK-antwoord is te groot.')
        try:
            data = json.loads(result.stdout)
        except ValueError:
            raise ControlError('SDK-reader gaf geen geldig antwoord. Controleer PHP en de plugininstallatie.') from None
        if result.returncode or data.get('error'):
            messages = {
                'selection_required': 'Kies een Miniserver op de Q-Brain-pagina.',
                'miniserver_missing': 'De gekozen Miniserver ontbreekt in LoxBerry.',
                'php_curl_missing': 'PHP curl ontbreekt. Installeer de plugin-update opnieuw.',
                'php_xml_missing': 'PHP XML ontbreekt. Installeer de plugin-update opnieuw.',
                'authentication': 'Miniserver weigert de aanmelding (HTTP 401/403). Controleer het centrale LoxBerry-account en de rechten.',
                'certificate': 'Het HTTPS-certificaat van de Miniserver wordt niet vertrouwd. Controleer het certificaat op de LoxBerry-host.',
                'timeout': 'De Miniserver antwoordt niet binnen de leestijd. Controleer de verbinding.',
                'connection': 'Geen verbinding met de Miniserver. Controleer adres, poort en bereikbaarheid in LoxBerry.',
                'structure_invalid': 'De Miniserver levert geen geldige LoxAPP3.json-structuur.',
                'http_error': 'De Miniserver retourneert een HTTP-fout bij het lezen van de configuratie.',
                'response_large': 'De Miniserver-respons overschrijdt de toegestane grootte.',
                'sdk_unavailable': 'LoxBerry SDK kon niet worden geladen. Controleer de plugininstallatie.',
            }
            code = data.get('error_code', 'sdk_unavailable')
            raise ControlError(messages.get(code, messages['sdk_unavailable']))
        return data

    def start_collector(self):
        directory = self.state / 'telemetry'
        directory.mkdir(mode=0o755, exist_ok=True)
        os.chmod(directory, 0o755)
        generation = secrets.token_hex(16)
        atomic_json(self.state / 'collector.json', {'generation': generation, 'miniserver_id': self.settings()['miniserver_id']})
        subprocess.Popen([sys.executable, '-I', str(self.runtime / 'control.py'), '_collect', generation],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, env=self.process_env())

    def collect(self, generation):
        import fcntl
        with (self.state / 'collector.lock').open('a') as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            self.collect_loop(generation)

    def collect_loop(self, generation):
        # One generation per start. Old collectors cannot overwrite the new generation.
        while read_json(self.state / 'collector.json', {}).get('generation') == generation:
            settings = self.settings()
            if not read_json(self.state / 'desired.json', {}).get('running'):
                return
            try:
                data = self.sdk('collect', read_json(self.state / 'collector.json', {})['miniserver_id'])
            except ControlError as error:
                data = {'timestamp': time.time(), 'error': str(error)}
            except Exception:
                data = {'timestamp': time.time(), 'error': 'SDK-reader niet beschikbaar of leestijd verstreken. Controleer de plugininstallatie.'}
            if read_json(self.state / 'collector.json', {}).get('generation') != generation:
                return
            destination = self.state / 'telemetry/snapshot.json'
            atomic_json(destination, data)
            os.chmod(destination, 0o644)
            for _ in range(12):
                time.sleep(5)
                if read_json(self.state / 'collector.json', {}).get('generation') != generation or not read_json(self.state / 'desired.json', {}).get('running'):
                    return

    def docker_available(self):
        try:
            subprocess.run(['/usr/bin/docker', 'compose', 'version'], check=True,
                           capture_output=True, timeout=3, env=self.process_env())
            subprocess.run(['/usr/bin/docker', 'info', '--format', '{{.ServerVersion}}'], check=True,
                           capture_output=True, timeout=3, env=self.process_env())
            return True
        except (OSError, subprocess.SubprocessError):
            return False

    def run(self, *args, timeout=1800):
        with self.log_file.open('ab') as log:
            # Fixed argument list; never use a shell or a browser-provided Compose file.
            subprocess.run(self.command(*args), check=True, stdout=log, stderr=log,
                           timeout=timeout, env=self.process_env())

    def schedule(self, action):
        settings = self.settings()
        with self.lock() as lockfd:
            if not self.docker_available():
                raise ControlError('Docker Engine with Compose v2 is missing or unavailable')
            if action in ('start', 'pull'):
                validate({}, settings)
                atomic_json(self.compose_file, compose_document(settings, self.runtime, self.folder))
            if action in ('start', 'stop'):
                atomic_json(self.state / 'desired.json', {'running': action == 'start'})
            atomic_json(self.job_file, {'action': action, 'status': 'running', 'started': time.time()})
            self.log_file.write_text('', encoding='utf-8')
            os.chmod(self.log_file, 0o600)
            subprocess.Popen([sys.executable, '-I', str(self.runtime / 'control.py'),
                                      '_worker', action, str(lockfd)],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True, pass_fds=(lockfd,), env=self.process_env())
        return {'accepted': True, 'action': action}

    def ensure_model(self):
        # An installed model works offline. Wait briefly for Ollama after container start.
        for attempt in range(15):
            try:
                subprocess.run(self.command('exec', '-T', 'ollama', 'ollama', 'list'),
                               check=True, capture_output=True, timeout=5, env=self.process_env())
                break
            except (OSError, subprocess.SubprocessError):
                if attempt == 14:
                    raise ControlError('Ollama start niet; controleer de servicelog.') from None
                time.sleep(2)
        try:
            self.run('exec', '-T', 'ollama', 'ollama', 'show', self.settings()['ollama_model'], timeout=30)
        except subprocess.CalledProcessError:
            self.run('exec', '-T', 'ollama', 'ollama', 'pull', self.settings()['ollama_model'], timeout=7200)

    def worker(self, action, lockfd):
        # The inherited flock remains held until this process exits.
        os.fstat(lockfd)
        try:
            if action == 'start':
                atomic_json(self.state / 'collector.json', {})
                if self.settings()['loxberry_sdk'] and not self.settings()['demo_mode']:
                    self.start_collector()
                self.run('build', 'qbox')
                self.run('up', '-d', '--no-build', 'qbox', 'ollama', 'agent')
                self.ensure_model()
                atomic_json(self.state / 'applied.json', {'revision': self.settings()['revision']})
            elif action == 'stop':
                if self.compose_file.exists():
                    self.run('down', '--remove-orphans', timeout=180)
            elif action == 'pull':
                self.run('up', '-d', 'ollama')
                self.run('exec', '-T', 'ollama', 'ollama', 'pull', self.settings()['ollama_model'], timeout=7200)
            else:
                raise ControlError('Invalid worker action')
            atomic_json(self.job_file, {'action': action, 'status': 'completed', 'finished': time.time()})
        except Exception:
            atomic_json(self.job_file, {'action': action, 'status': 'failed', 'finished': time.time()})
        finally:
            os.close(lockfd)

    def status(self):
        settings = self.settings()
        ready = False
        overview = {}
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{settings['mcp_port']}/overview",
                       headers={'Authorization': 'Bearer ' + settings['mcp_token']})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(request, timeout=3) as response:
                ready = response.status == 200
                overview = json.load(response)
        except (OSError, ValueError):
            pass
        service_available = ready
        ready = ready and any(row.get('kind') == 'advice' and
            0 <= time.time() - row.get('timestamp', 0) <= settings['reasoning_interval_seconds'] + 180
            for row in overview.get('history', []))
        job = read_json(self.job_file, {})
        if job.get('status') == 'running':
            # A killed worker or power loss must not leave a permanent busy indicator.
            try:
                with self.lock():
                    job = {**job, 'status': 'interrupted'}
            except ControlError:
                pass
        return {'ready': ready, 'service_available': service_available, 'overview': overview, 'sdk': {'error': read_json(self.state / 'telemetry/snapshot.json', {}).get('error')}, 'docker_available': self.docker_available(), 'observe_only': True,
                'demo_mode': settings['demo_mode'], 'job': job,
                'pending_changes': read_json(self.state / 'applied.json', {}).get('revision') != settings['revision'],
                'desired_running': read_json(self.state / 'desired.json', {}).get('running', False)}

    def logs(self):
        if not self.log_file.exists():
            return {'text': ''}
        with self.log_file.open('rb') as log:
            log.seek(max(0, self.log_file.stat().st_size - 24000))
            text = log.read(24000).decode('utf-8', errors='replace')
        for key in ('mcp_token', 'loxone_password', 'loxone_username'):
            secret = self.settings().get(key)
            if secret:
                text = text.replace(secret, '[redacted]')
        return {'text': text}

    def dispatch(self, action):
        if action == 'initialize':
            with self.lock():
                self.settings()
            return {'initialized': True}
        if action == 'config':
            config = public_config(self.settings())
            try:
                config.update(self.sdk('list'))
            except ControlError as error:
                config.update(miniservers=[], sdk_error=str(error))
            return config
        if action == 'save':
            raw = sys.stdin.read(32769)
            if len(raw) > 32768:
                raise ControlError('Configuration request too large')
            with self.lock():
                old = self.settings()
                new = validate(json.loads(raw), old)
                atomic_json(self.settings_file, {**new, 'mcp_token': old['mcp_token'], 'revision': old['revision'] + 1})
            return {'saved': True, 'restart_required': True}
        if action == 'status':
            return self.status()
        if action == 'logs':
            return self.logs()
        if action in ('start', 'stop', 'pull'):
            return self.schedule(action)
        if action == 'boot':
            if read_json(self.state / 'desired.json', {}).get('running'):
                return self.schedule('start')
            return {'started': False}
        if action == 'prepare_upgrade':
            with self.lock():
                atomic_json(self.state / 'collector.json', {})
                if self.compose_file.exists():
                    self.run('down', '--remove-orphans', timeout=180)
            return {'stopped_for_upgrade': True}
        if action == 'uninstall':
            with self.lock():
                atomic_json(self.state / 'collector.json', {})
                if self.compose_file.exists():
                    self.run('down', '--remove-orphans', timeout=180)
                atomic_json(self.state / 'desired.json', {'running': False})
                (Path('/etc/sudoers.d') / ('qbrain-' + self.folder)).unlink(missing_ok=True)
                if self.runtime.parent != Path('/usr/local/lib/qbrain'):
                    raise ControlError('Unexpected uninstall target')
                shutil.rmtree(self.runtime)
            return {'removed': True, 'data_retained': True}
        raise ControlError('Unsupported action')


def main():
    if os.geteuid() != 0:
        raise ControlError('This installed controller must run as root')
    if len(sys.argv) < 2 or sys.argv[1] not in ACTIONS:
        raise ControlError('Unsupported action')
    controller = Controller(Path(__file__).parent)
    if sys.argv[1] == '_collect':
        if len(sys.argv) != 3 or not re.fullmatch(r'[a-f0-9]{32}', sys.argv[2]):
            raise ControlError('Invalid collector generation')
        controller.collect(sys.argv[2])
        return
    if sys.argv[1] == '_worker':
        if len(sys.argv) != 4:
            raise ControlError('Invalid worker arguments')
        controller.worker(sys.argv[2], int(sys.argv[3]))
        return
    if len(sys.argv) != 2:
        raise ControlError('Unexpected arguments')
    print(json.dumps(controller.dispatch(sys.argv[1])))


if __name__ == '__main__':
    try:
        main()
    except ControlError as error:
        print(json.dumps({'error': str(error)}))
        sys.exit(1)
    except Exception:
        print(json.dumps({'error': 'Q-Brain operation failed; check installation and configuration'}))
        sys.exit(1)
