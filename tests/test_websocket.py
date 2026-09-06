"""Real PHP WebSocket reader against a local TLS Miniserver protocol fixture."""
import base64
import hashlib
import hmac
import json
import ssl
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from test_discovery import sdk, UUID

STATE = '01020304-0506-0708-090a0b0c0d0e0f10'
STORAGE = '11223344-5566-7788-9900aabbccddeeff'


def certificate(directory):
    import datetime
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'wrong-host.local')])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1))
          .not_valid_after(now+datetime.timedelta(days=1)).sign(key,hashes.SHA256()))
    certfile=directory/'ws-cert.pem'; keyfile=directory/'ws-key.pem'
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(certfile,keyfile)
    return context


def event(uuid, value):
    a,b,c,d=uuid.split('-')
    return struct.pack('<IHH',int(a,16),int(b,16),int(c,16))+bytes.fromhex(d)+struct.pack('<d',value)


@pytest.mark.parametrize('algorithm', ['SHA256', 'SHA1'])
def test_ws_reads_meter_states_and_revokes_only_own_token(sdk, algorithm):
    (sdk.root/'libs/phplib/loxberry_io.php').write_text('''<?php
function mshttp_call2($id,$path,$options) {
return [json_encode(['controls'=>['''+json.dumps(UUID)+'''=>['name'=>'Battery 1','type'=>'Meter',
'details'=>['type'=>'storage','actualFormat'=>'%.2f kW','storageFormat'=>'%.1f kWh','storageMax'=>10],
'states'=>['actual'=>'''+json.dumps(STATE)+''','storage'=>'''+json.dumps(STORAGE)+''']]]]), ['code'=>200,'error'=>0]];
}
''')
    commands=[]; masked=[]; failures=[]
    key='0123456789abcdef0123456789abcdef'
    class Miniserver(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args): pass
        def sendframe(self,data,opcode=2,fin=True):
            n=len(data)
            header=bytes([(128 if fin else 0)|opcode])+ (bytes([n]) if n<126 else b'\x7e'+struct.pack('>H',n))
            self.wfile.write(header+data);self.wfile.flush()
        def response(self,value,control):
            payload=json.dumps({'LL':{'Code':'200','control':control,'value':value}}).encode()
            self.sendframe(b'\x03\x00\x00\x00'+struct.pack('<I',len(payload)))
            self.sendframe(payload,1)
        def do_GET(self):
            try:
                assert self.path=='/ws/rfc6455'
                assert self.headers['Sec-WebSocket-Protocol']=='remotecontrol'
                accept=base64.b64encode(hashlib.sha1((self.headers['Sec-WebSocket-Key']+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
                self.send_response(101);self.send_header('Upgrade','websocket');self.send_header('Connection','Upgrade');self.send_header('Sec-WebSocket-Accept',accept);self.end_headers()
                while True:
                    head=self.rfile.read(2)
                    if not head: break
                    opcode=head[0]&15; n=head[1]&127
                    assert head[1]&128
                    if n==126: n=struct.unpack('>H',self.rfile.read(2))[0]
                    mask=self.rfile.read(4); data=self.rfile.read(n)
                    payload=bytes(x^mask[i%4] for i,x in enumerate(data))
                    masked.append(True)
                    if opcode==10: continue
                    command=payload.decode();commands.append(command)
                    if command.startswith('jdev/sys/getkey2/'):
                        self.response({'key':key,'salt':'user-salt','hashAlg':algorithm},command)
                    elif command.startswith('jdev/sys/getjwt/'):
                        parts=command.split('/')
                        pw=hashlib.new(algorithm.lower(),b'hidden-password:user-salt').hexdigest().upper()
                        expected=hmac.new(bytes.fromhex(key),('hidden-user:'+pw).encode(),algorithm.lower()).hexdigest()
                        assert parts[3]==expected and parts[4]=='hidden-user' and parts[5]=='2'
                        self.response({'token':'test-session-jwt','validUntil':99999999},command)
                    elif command=='jdev/sps/enablebinstatusupdate':
                        self.response('1',command)
                        payload=event(STATE,-2.5)+event(STORAGE,6.2)+event('ffffffff-ffff-ffff-ffffffffffffffff',999)
                        self.sendframe(b'\x03\x02\x01\x00'+struct.pack('<I',len(payload)+100)) # estimated size
                        self.sendframe(b'\x03\x02\x00\x00'+struct.pack('<I',len(payload)))
                        self.sendframe(payload[:17],2,False)
                        self.sendframe(b'ping',9)
                        self.sendframe(payload[17:],0,True)
                    elif command=='jdev/sys/getkey': self.response(key,command)
                    elif command.startswith('jdev/sys/killtoken/'):
                        assert command.split('/')[3]==hmac.new(bytes.fromhex(key),b'test-session-jwt',algorithm.lower()).hexdigest()
                        self.response('1',command)
                        break
                    else: raise AssertionError('Unexpected command')
            except Exception as exc: failures.append(type(exc).__name__)
            finally: self.close_connection=True
    server=ThreadingHTTPServer(('127.0.0.1',0),Miniserver)
    server.socket=certificate(sdk.root).wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        result,_=sdk(SDK_ORIGIN=f'https://hidden-user:hidden-password@127.0.0.1:{server.server_port}')
        assert result.returncode==0,result.stdout+result.stderr
        data=json.loads(result.stdout)
        assert data['websocket']['error'] is None, data
        assert data['readings'][0]['value']==-2.5
        assert data['readings'][0]['state_values']=={'actual':-2.5,'storage':6.2}
        assert len(commands)==5 and commands[-1].startswith('jdev/sys/killtoken/')
        assert masked and not failures
        assert all('sps/io' not in x for x in commands)
        assert 'hidden-password' not in result.stdout and 'test-session-jwt' not in result.stdout
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
