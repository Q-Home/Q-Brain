import json
import pytest
import httpx
from qbox.discovery_ai import DiscoveryAnalysis, inventory, validated_proposals, fingerprint
from qbox.ollama import OllamaClient
from qbox.config import Settings


def test_model_cannot_invent_signals_or_turn_settings_into_measurements():
    rows=inventory({'readings':[
        {'id':'meter','name':'Grid','type':'Meter','format':'%.1f kW','states':{'actual':'uuid'},'state_values':{'actual':1.2}},
        {'id':'slider','name':'MaximumBattery','type':'Slider','states':{'position':'id'},'state_values':{'position':90}},
    ]})
    proposal=lambda id,state,role: {'control_id':id,'state':state,'role':role,'confidence':'high','reason':'Candidate'}
    data=DiscoveryAnalysis(summary='Discovery',proposals=[proposal('meter','actual','grid_power'),proposal('invented','actual','pv_power'),
        proposal('meter','missing','pv_power'),proposal('slider','position','battery_soc')],missing_information=['Polarity'])
    result=validated_proposals(data,rows)
    assert len(result['proposals'])==1 and result['rejected_proposals']==3
    assert result['proposals'][0]['automatically_applied'] is False
    assert result['proposals'][0]['measured_value']==1.2
    other=json.loads(json.dumps(rows));other[0]['values']['actual']=3
    assert fingerprint(rows,'model')==fingerprint(other,'model')
    other[0]['values']['actual']=None
    assert fingerprint(rows,'model')!=fingerprint(other,'model')


async def test_dedicated_model_runs_without_any_live_energy_values():
    seen=[]
    def respond(request):
        data=json.loads(request.content);seen.append(data)
        return httpx.Response(200,json={'message':{'content':json.dumps({'summary':'Meter gevonden, actuele waarden ontbreken.',
            'proposals':[{'control_id':'grid','state':'actual','role':'grid_power','confidence':'medium','reason':'Meternaam'}],
            'missing_information':['Actuele WebSocket-waarden']})}})
    client=OllamaClient(Settings(mcp_token='x'*32,discovery_model='qbrain-discovery:latest'),transport=httpx.MockTransport(respond))
    try:
        result=await client.discover(inventory({'readings':[{'id':'grid','name':'Grid','type':'Meter','states':{'actual':'uuid'},'state_values':{'actual':None}}]}))
        assert result['proposals'][0]['measured_value'] is None
        assert seen[0]['model']=='qbrain-discovery:latest'
        assert 'tools' not in seen[0]
    finally: await client.close()


async def test_multiple_wallboxes_and_storage_can_be_analyzed_individually(tmp_path):
    import time
    from qbox.discovery import LoxBerryAdapter
    path=tmp_path/'snapshot.json'
    devices=[{'id':f'ev-{i}','name':f'EV-{i}','type':'Wallbox2','format':'%.1f kW','status':'read',
              'value':i+1,'states':{'actual':f'uuid-{i}'},'state_values':{'actual':i+1}} for i in range(4)]
    devices.append({'id':'battery','name':'Battery 1','type':'Meter','format':'%.1f kW','status':'read','value':-2,
                    'details':{'type':'storage','storageFormat':'%.1f kWh'},'state_values':{'actual':-2,'storage':6}})
    path.write_text(json.dumps({'timestamp':time.time(),'readings':devices}))
    adapter=LoxBerryAdapter(Settings(mcp_token='x'*32,demo_mode=False,loxberry_snapshot_path=str(path)))
    snapshot=await adapter.snapshot()
    assert snapshot.ev_power is None  # no invented site total
    assert snapshot.battery_soc is None
    assert len(snapshot.observations)==6
    assert snapshot.observations[0].value==1000 and snapshot.observations[0].unit=='W'
    assert snapshot.observations[-2].direction=='unknown'
    assert snapshot.observations[-1].unit=='kWh'
