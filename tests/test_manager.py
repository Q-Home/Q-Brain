import math
import pytest
from qbox.discovery import discover
from qbox.ollama import analysis_failure
import httpx


def manager(**values):
    return {'id':'manager','name':'Energie manager','type':'EnergyManager2','state_values':values,'details':{}}


def test_real_manager_fields_and_charging_sign():
    values, report=discover({'readings':[manager(Gpwr=.72, Spwr=-2, Ppwr=0, Ssoc=99.64538828531902),
        {'id':'pv','type':'Meter','name':'Solar','format':'%.3fkW','status':'read','value':1}]})
    assert values == {'grid_power':720, 'battery_power':2000, 'pv_power':0, 'battery_soc':99.64538828531902, 'ev_power':None}
    assert report['grid_power']['candidates'][0]['state']=='Gpwr'


def test_multiple_managers_are_not_summed():
    values, report=discover({'readings':[manager(Gpwr=1),manager(Gpwr=2)]})
    assert values['grid_power'] is None
    assert report['grid_power']['status']=='ambiguous'


def test_manager_invalid_and_disconnected_states():
    item=manager(Gpwr=math.inf, Spwr=0, Ppwr=-1, Ssoc=101)
    item['details']={'HasSpwr':False}
    values, report=discover({'readings':[item]})
    assert all(v is None for v in values.values())
    assert report['grid_power']['value'] is None
    assert report['battery_power']['status']=='missing'


def test_empty_php_details_array_does_not_break_observations():
    from qbox.discovery import observations
    rows=observations({'readings':[{'id':'meter','type':'Meter','details':[], 'format':'%.3fkW','state_values':{'actual':.72}}]})
    assert rows[0].value==720


def test_model_errors_are_specific_without_response_secrets():
    request=httpx.Request('POST','http://ollama/api/chat')
    error=httpx.HTTPStatusError('secret',request=request,response=httpx.Response(404,request=request,text='secret'))
    assert analysis_failure(error)['code']=='model_http_404'
    assert 'secret' not in str(analysis_failure(error))
    assert analysis_failure(httpx.ReadTimeout('secret'))['code']=='model_timeout'


def test_memory_error_is_classified_without_exposing_server_text():
    request=httpx.Request('POST','http://ollama/api/chat')
    response=httpx.Response(500,request=request,json={'error':'model requires more system memory: secret'})
    result=analysis_failure(httpx.HTTPStatusError('secret',request=request,response=response))
    assert result['code']=='model_memory'
    assert 'secret' not in str(result)
