"""Conservative semantic discovery from the host SDK's credential-free readings."""
import json
import re
import time
from pathlib import Path
from .models import Snapshot

KEYS = ('grid_power', 'pv_power', 'battery_soc', 'battery_power', 'ev_power')


def discover(document):
    candidates = {key: [] for key in KEYS}
    for item in document.get('readings', [])[:100]:
        name = str(item.get('name', '')).lower()
        fmt = str(item.get('format', '')).strip()
        # Ignore printf placeholders before inspecting the actual unit.
        unit = re.sub(r'%[-+0-9.]*[fdi]', '', fmt).strip()
        unit = unit.replace('%%', '%')
        factor = {'W': 1, 'kW': 1000, '%': 1}.get(unit)
        if factor is None or item.get('status') != 'read':
            continue
        value = item.get('value')
        if type(value) not in (int, float):
            continue
        keys = []
        if unit == '%' and re.search(r'batter|accu|\bsoc\b', name):
            keys.append('battery_soc')
        if unit in ('W', 'kW'):
            if re.search(r'\bpv\b|solar|zonne|photovolta', name): keys.append('pv_power')
            if re.search(r'laadpaal|wallbox|\bev\b', name): keys.append('ev_power')
            # Polarity is explicit in the configured name; never infer it from one sample.
            if re.search(r'grid|netvermogen|netz', name) and 'positive import' in name: keys.append('grid_power')
            if re.search(r'batter|accu', name) and 'positive charging' in name: keys.append('battery_power')
        if len(keys) == 1:
            candidates[keys[0]].append({**item, 'normalized_value': value * factor})
    values, report = {}, {}
    for key, items in candidates.items():
        report[key] = {'status': 'found' if len(items) == 1 else 'ambiguous' if items else 'missing',
                       'candidates': [{'id': x['id'], 'name': x['name']} for x in items]}
        values[key] = items[0]['normalized_value'] if len(items) == 1 else None
        if values[key] is not None and (not __import__('math').isfinite(values[key]) or
                (key in ('pv_power', 'ev_power', 'battery_soc') and values[key] < 0) or
                (key == 'battery_soc' and values[key] > 100)):
            values[key] = None
            report[key]['status'] = 'invalid'
    return values, report


class LoxBerryAdapter:
    def __init__(self, config):
        self.path = Path(config.loxberry_snapshot_path)

    def document(self):
        if self.path.stat().st_size > 1048576:
            raise ValueError('Oversized SDK telemetry')
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('error') or not 0 <= time.time() - data['timestamp'] <= 180:
            raise ValueError('SDK telemetry unavailable or stale')
        return data

    async def snapshot(self):
        data = self.document()
        values, _ = discover(data)
        if not any(v is not None for v in values.values()):
            raise ValueError('No unambiguous supported energy readings found')
        return Snapshot(timestamp=data['timestamp'], source='loxone', **values)

    async def discovery(self):
        data = self.document()
        _, report = discover(data)
        return {'signals': report, 'readings': data.get('readings', []),
                'timestamp': data['timestamp'], 'truncated': data.get('truncated', False)}

    async def close(self):
        pass
