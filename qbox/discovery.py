"""Conservative semantic discovery from the host SDK's credential-free readings."""
import json
import math
import re
import time
from pathlib import Path
from .models import Snapshot, Observation

MANAGER_FIELDS = {'Gpwr': ('grid_power', 1000), 'Ppwr': ('pv_power', 1000),
                  'Spwr': ('battery_power', -1000), 'Ssoc': ('battery_soc', 1)}


def manager_candidates(item):
    live = item.get('state_values') or {}
    details = item.get('details') or {}
    for state, (role, factor) in MANAGER_FIELDS.items():
        if state in ('Spwr', 'Ssoc') and details.get('Has' + state) in (False, 0):
            continue
        value = live.get(state)
        if type(value) in (int, float):
            yield role, {**item, 'state': state, 'normalized_value': value * factor}


KEYS = ('grid_power', 'pv_power', 'battery_soc', 'battery_power', 'ev_power')


def discover(document):
    candidates = {key: [] for key in KEYS}
    for item in document.get('readings', [])[:100]:
        if item.get('type') == 'EnergyManager2':
            for role, candidate in manager_candidates(item):
                candidates[role].append(candidate)
            continue
        name = str(item.get('name', '')).lower()
        fmt = str(item.get('format', '')).strip()
        # Ignore printf placeholders before inspecting the actual unit.
        unit = re.sub(r'%[-+0-9.]*[fdi]', '', fmt).strip()
        unit = unit.replace('%%', '%')
        factor = {'W': 1, 'kW': 1000, '%': 1}.get(unit)
        if item.get('type') not in (None, 'InfoOnlyAnalog', 'Meter', 'Wallbox2'):
            continue
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
            if item.get('type') == 'Wallbox2' or re.search(r'laadpaal|wallbox|\bev\b', name): keys.append('ev_power')
            # Polarity is explicit in the configured name; never infer it from one sample.
            if re.search(r'grid|netvermogen|netz', name) and 'positive import' in name: keys.append('grid_power')
            if re.search(r'batter|accu', name) and 'positive charging' in name: keys.append('battery_power')
        if len(keys) == 1:
            candidates[keys[0]].append({**item, 'normalized_value': value * factor})
    values, report = {}, {}
    for key, items in candidates.items():
        # Explicit block semantics take precedence over names of component meters.
        managers = [x for x in items if x.get('type') == 'EnergyManager2']
        items = managers or items
        report[key] = {'status': 'found' if len(items) == 1 else 'ambiguous' if items else 'missing',
                       'candidates': [{'id': x['id'], 'name': x['name'], 'state': x.get('state')} for x in items],
                       'value': items[0]['normalized_value'] if len(items) == 1 else None,
                       'unit': '%' if key == 'battery_soc' else 'W'}
        values[key] = items[0]['normalized_value'] if len(items) == 1 else None
        if values[key] is not None and (not math.isfinite(values[key]) or
                (key in ('pv_power', 'ev_power', 'battery_soc') and values[key] < 0) or
                (key == 'battery_soc' and values[key] > 100)):
            values[key] = None
            report[key]['status'] = 'invalid'
            report[key]['value'] = None
    return values, report


def observations(document):
    result=[]
    for item in document.get('readings', [])[:100]:
        if item.get('type') not in ('Meter','Wallbox2','InfoOnlyAnalog'):
            continue
        fields={'actual': item.get('format','')} if item.get('type') in ('Meter','Wallbox2') else {'value':item.get('format','')}
        if item.get('type') == 'Meter' and (item.get('details') or {}).get('type') == 'storage':
            fields['storage']=(item.get('details') or {}).get('storageFormat','')
        live=item.get('state_values') or {'value':item.get('value')}
        for field, fmt in fields.items():
            unit=re.sub(r'%[-+0-9.]*[fdi]', '',str(fmt)).strip().replace('%%','%')
            value=live.get(field)
            if type(value) not in (int,float) or not math.isfinite(value):
                continue
            if unit in ('W','kW') and field in ('actual','value'):
                value*=1000 if unit=='kW' else 1; unit='W'; quantity='power'
            elif field=='storage' and unit in ('Wh','kWh','%') and value>=0:
                quantity='soc' if unit=='%' else 'stored_energy'
                if unit=='%' and value>100: continue
            else: continue
            result.append(Observation(control_id=item['id'],name=str(item.get('name',''))[:128],state=field,
                          quantity=quantity,value=value,unit=unit,
                          direction='consumption' if item.get('type')=='Wallbox2' else 'unknown'))
    return result[:100]


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
        measured=observations(data)
        if not measured and not any(v is not None for v in values.values()):
            raise ValueError('No unambiguous supported energy readings found')
        return Snapshot(timestamp=data['timestamp'], source='loxone', observations=measured, **values)

    async def discovery(self):
        data = self.document()
        _, report = discover(data)
        return {'signals': report, 'readings': data.get('readings', []),
                'timestamp': data['timestamp'], 'truncated': data.get('truncated', False), 'websocket':data.get('websocket',{})}

    async def close(self):
        pass
