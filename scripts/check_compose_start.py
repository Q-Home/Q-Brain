"""CI smoke test: build the local image, then start both services without registry pulls."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('control', ROOT / 'bin/control.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)

with tempfile.TemporaryDirectory() as temporary:
    settings = {**control.DEFAULTS, 'demo_mode': True, 'mcp_token': 'ci-test-token-' + 'x'*32, 'revision': 1}
    compose = control.compose_document(settings, ROOT, 'qbrainci')
    # No model download/inference in this smoke test; MCP liveness needs no upstream.
    del compose['services']['ollama']
    compose['services']['qbox']['build'] = str(ROOT)
    compose['services']['qbox']['ports'] = []
    path = Path(temporary) / 'compose.json'
    path.write_text(json.dumps(compose), encoding='utf-8')
    command = ['docker', 'compose', '-p', 'qbrain-start-ci', '-f', str(path)]
    try:
        subprocess.run([*command, 'build', 'qbox'], check=True, timeout=600)
        subprocess.run([*command, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '90', 'qbox'], check=True, timeout=150)
        subprocess.run([*command, 'up', '-d', '--no-build', 'agent'], check=True, timeout=90)
        result = subprocess.run([*command, 'ps', '--services', '--status', 'running'], check=True, capture_output=True, text=True)
        assert set(result.stdout.split()) == {'qbox', 'agent'}, result.stdout
        print('Local image built; MCP and agent running with pull_policy=never.')
    finally:
        subprocess.run([*command, 'down', '-v', '--remove-orphans'], check=True, timeout=90)
