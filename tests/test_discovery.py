"""SDK contract tests use actual PHP with fixture LoxBerry libraries; no Miniserver needed."""
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from qbox.config import Settings
from qbox.discovery import LoxBerryAdapter, discover
from qbox.ollama import OllamaClient
import httpx

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_BINARY') or shutil.which('php')
UUID = '12345678-1234-1234-1234567890123456'


def document(*readings):
    return {'timestamp': time.time(), 'readings': list(readings), 'error': None}


def reading(name='PV vermogen', value=2.5, fmt='%.2f kW', uuid=UUID):
    return {'id': uuid, 'name': name, 'type': 'InfoOnlyAnalog', 'format': fmt, 'value': value, 'status': 'read'}


def test_discovery_units_ambiguity_and_polarity():
    values, report = discover(document(reading(), reading('Batterij SOC', 62, '%.0f %%'),
                                       reading('Netvermogen', -3)))
    assert values['pv_power'] == 2500 and values['battery_soc'] == 62
    assert values['grid_power'] is None and values['ev_power'] is None
    values, report = discover(document(reading(), reading(uuid='another')))
    assert values['pv_power'] is None and report['pv_power']['status'] == 'ambiguous'
    assert discover(document(reading(fmt='%.1f kWh')))[0]['pv_power'] is None
    assert discover(document(reading(value=-1)))[0]['pv_power'] is None
    assert discover(document(reading('Grid power positive import', -1)))[0]['grid_power'] == -1000


async def test_partial_snapshot_and_staleness(tmp_path):
    path = tmp_path / 'snapshot.json'
    path.write_text(json.dumps(document(reading())))
    config = Settings(mcp_token='x'*32, demo_mode=False, loxberry_snapshot_path=str(path))
    adapter = LoxBerryAdapter(config)
    snapshot = await adapter.snapshot()
    assert snapshot.pv_power == 2500 and snapshot.grid_power is None
    path.write_text(json.dumps({**document(reading()), 'timestamp': time.time()-181}))
    with pytest.raises(ValueError, match='stale'): await adapter.snapshot()
    path.write_text(json.dumps(document()))
    with pytest.raises(ValueError, match='No unambiguous'): await adapter.snapshot()
    with pytest.raises(ValueError): Settings(mcp_token='x'*32, loxberry_snapshot_path=str(path), demo_mode=False, observe_only=False)


async def test_partial_advice_cannot_recommend_ev_power(tmp_path):
    config = Settings(mcp_token='x'*32)
    def response(request):
        return httpx.Response(200, json={'message': {'content': json.dumps({'summary': 'Observation', 'confidence': 'high', 'suggested_ev_limit_w': 1100, 'reasons': []})}})
    from qbox.models import Snapshot
    client = OllamaClient(config, transport=httpx.MockTransport(response))
    try:
        advice = await client.reason(Snapshot(timestamp=time.time(), source='loxone', pv_power=2000))
        assert advice.confidence == 'low' and advice.suggested_ev_limit_w is None
    finally: await client.close()


@pytest.fixture
def sdk(tmp_path):
    if not PHP: pytest.skip('PHP not available')
    libs = tmp_path / 'libs/phplib'; libs.mkdir(parents=True)
    shutil.copy(ROOT / 'bin/loxberry.php', tmp_path / 'loxberry.php')
    (tmp_path / 'installation.json').write_text(json.dumps({'home': str(tmp_path)}))
    (libs / 'loxberry_system.php').write_text('''<?php
class LBSystem { static function get_miniservers() {
$servers = ['1' => ['Name'=>'Home', 'Admin'=>'hidden-user', 'Pass'=>'hidden-password']];
if (getenv('SDK_MULTI')) $servers['2'] = ['Name'=>'Office'];
return $servers;
} }
''')
    (libs / 'loxberry_io.php').write_text('''<?php
function mshttp_call2($id, $path, $options) {
file_put_contents(getenv('SDK_TRACE'), json_encode([$id, $path, $options])."\\n", FILE_APPEND);
if ($path === '/data/LoxAPP3.json') return [json_encode(['controls'=>[
'12345678-1234-1234-1234567890123456'=>['name'=>'PV vermogen','type'=>'InfoOnlyAnalog','details'=>['format'=>'%.2f kW']],
'../../On'=>['name'=>'PV injection','type'=>'InfoOnlyAnalog'],
'22345678-1234-1234-1234567890123456'=>['name'=>'Batterij','type'=>'Meter']
]]), ['code'=>200,'error'=>0]];
if (getenv('SDK_BAD')) return ['<LL Code="200" value="3"><output name="P" value="1500"/></LL>', ['code'=>200,'error'=>0]];
return ['<LL Code="200" value="0"/>', ['code'=>200,'error'=>0]];
}
''')
    def run(action='collect', selected='', **env):
        trace = tmp_path / 'trace.jsonl'
        trace.write_text('')
        result = subprocess.run([PHP, str(tmp_path / 'loxberry.php'), action, selected],
                                env={**os.environ, 'SDK_TRACE': str(trace), **env}, capture_output=True, text=True, timeout=5)
        return result, [json.loads(line) for line in trace.read_text().splitlines()]
    return run


def test_sdk_lists_without_credentials_or_network(sdk):
    result, calls = sdk('list')
    assert result.returncode == 0 and not calls
    assert json.loads(result.stdout) == {'miniservers': [{'id':'1', 'name':'Home'}]}
    assert 'hidden-' not in result.stdout


def test_sdk_uses_only_discovered_scalar_read_commands(sdk):
    result, calls = sdk()
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data['readings'][0]['value'] == 0  # real zero survives the SDK fallback getter
    assert data['readings'][1]['status'] == 'unsupported_control'
    assert [x[1] for x in calls] == ['/data/LoxAPP3.json', f'/dev/sps/io/{UUID}/all', f'/dev/sps/io/{UUID}']
    assert all(x[2]['ssl_verify_mode'] == 1 and x[2]['timeout'] == 3 for x in calls)
    assert 'hidden-' not in result.stdout


def test_sdk_multiple_servers_require_selection_and_reject_block_response(sdk):
    result, calls = sdk(SDK_MULTI='1')
    assert result.returncode == 1 and not calls
    result, calls = sdk(selected='2', SDK_MULTI='1', SDK_BAD='1')
    assert result.returncode == 0 and all(x[0] == '2' for x in calls)
    assert json.loads(result.stdout)['readings'][0]['value'] is None
    result, calls = sdk(selected='../On')
    assert result.returncode == 1 and not calls
