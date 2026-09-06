"""Exercise the real PHP request/CSRF boundary with stubbed LoxBerry libraries."""
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_BINARY') or shutil.which('php')
pytestmark = pytest.mark.skipif(not PHP, reason='PHP CLI not available')


@pytest.fixture
def php_page(tmp_path):
    (tmp_path / 'loxberry_system.php').write_text("<?php $lbpconfigdir='/opt/loxberry/config/plugins/qbrain01'; $lbptemplatedir=getenv('QBRAIN_TEST_TEMPLATES');")
    (tmp_path / 'loxberry_web.php').write_text("<?php class LBWeb { static function lbheader(...$args) { echo '<!doctype html><html><body>'; } static function lbfooter() { echo '</body></html>'; } }")
    (tmp_path / 'loxberry_log.php').write_text('<?php')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    url = f'http://127.0.0.1:{port}/index.php'
    process = subprocess.Popen([PHP, '-d', 'include_path=' + str(tmp_path), '-d', 'session.save_path=' + str(tmp_path),
                                '-S', f'127.0.0.1:{port}', '-t', str(ROOT / 'webfrontend/htmlauth')],
                               env={**os.environ, 'QBRAIN_TEST_TEMPLATES': str(ROOT / 'templates')},
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = httpx.Client(trust_env=False)
    try:
        for _ in range(50):
            try:
                response = client.get(url)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.1)
        else:
            pytest.fail('PHP test server did not start')
        yield client, url, response
    finally:
        client.close()
        process.terminate()
        process.wait(timeout=5)


def test_php_page_uses_design_system_and_never_embeds_credentials(php_page):
    _, _, response = php_page
    assert 'lb-form-row' in response.text and 'lb-input' in response.text
    assert 'Observe-only' in response.text
    assert 'MCP_TOKEN' not in response.text
    assert 'Cache-Control' in response.headers and 'no-store' in response.headers['Cache-Control']
    assert 'HttpOnly' in response.headers['Set-Cookie']


def test_php_rejects_mutations_without_csrf(php_page):
    client, url, response = php_page
    token = re.search(r'const csrf = "([a-f0-9]{64})"', response.text).group(1)
    assert client.get(url + '?action=chat').status_code == 403
    assert client.post(url + '?action=chat', json={'op':'models'}).status_code == 403
    assert client.get(url + '?action=start').status_code == 403
    assert client.post(url + '?action=start', json={}).status_code == 403
    assert client.post(url + '?action=start', headers={'X-QBrain-CSRF': 'wrong'}, json={}).status_code == 403
    # Correct CSRF reaches input validation; malformed JSON is rejected before controller invocation.
    valid = client.post(url + '?action=save', headers={'X-QBrain-CSRF': token}, content='not-json')
    assert valid.status_code == 400 and 'error' in valid.json()


def test_php_rejects_unknown_actions(php_page):
    client, url, _ = php_page
    assert client.get(url + '?action=exec').status_code == 400
    assert client.get(url + '?action[]=start').status_code == 400
