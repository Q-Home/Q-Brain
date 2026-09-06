<?php
/** Bounded read-only Loxone WebSocket session. Credentials and JWT stay in PHP memory. */
declare(strict_types=1);
final class QBrainSocket {
    private $stream;
    private float $deadline;
    private array $wanted;
    public array $values = [];
    private ?int $kind = null;
    private ?int $size = null;
    private int $received = 0;
    public function __construct(array $server, array $wanted) {
        $this->deadline = microtime(true) + 18;
        $this->wanted = array_fill_keys(array_map('strtolower', $wanted), true);
        $uri = parse_url((string)($server['FullURI'] ?? ''));
        if (!$uri || !in_array($uri['scheme'] ?? '', ['http','https'], true)) { throw new QBrainReadError('connection'); }
        $tls = $uri['scheme'] === 'https';
        $host = trim((string)$uri['host'], '[]');
        if (preg_match('/[\r\n]/', $host)) { throw new QBrainReadError('connection'); }
        $port = (int)($uri['port'] ?? ($tls ? 443 : 80));
        $address = strpos($host, ':') !== false ? '['.$host.']' : $host;
        $context = stream_context_create(['ssl'=>['verify_peer'=>false,'verify_peer_name'=>false,'allow_self_signed'=>true, 'peer_name'=>$host]]);
        $this->stream = @stream_socket_client(($tls ? 'tls' : 'tcp').'://'.$address.':'.$port, $errno, $error, 3, STREAM_CLIENT_CONNECT, $context);
        if (!$this->stream) { throw new QBrainReadError('connection'); }
        stream_set_timeout($this->stream, 3);
        $key = base64_encode(random_bytes(16));
        $this->write("GET /ws/rfc6455 HTTP/1.1\r\nHost: $address:$port\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: $key\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: remotecontrol\r\n\r\n");
        $headers = '';
        while (strpos($headers, "\r\n\r\n") === false && strlen($headers) < 16384) { $headers .= $this->read(1); }
        $accept = base64_encode(sha1($key.'258EAFA5-E914-47DA-95CA-C5AB0DC85B11', true));
        if (!preg_match('~^HTTP/1\.[01] 101\b~', $headers) || !preg_match('/^Sec-WebSocket-Accept:\s*'.preg_quote($accept,'/').'\s*$/mi', $headers)) {
            $this->close(); throw new QBrainReadError('ws_upgrade');
        }
    }
    private function read(int $size): string {
        $data = '';
        while (strlen($data) < $size) {
            if (microtime(true) >= $this->deadline) { throw new QBrainReadError('timeout'); }
            $part = fread($this->stream, $size - strlen($data));
            if ($part === false || $part === '') { throw new QBrainReadError('timeout'); }
            $data .= $part;
        }
        $this->received += strlen($data);
        if ($this->received > 16777216) { throw new QBrainReadError('response_large'); }
        return $data;
    }
    private function write(string $data): void {
        while ($data !== '') {
            if (microtime(true) >= $this->deadline) { throw new QBrainReadError('timeout'); }
            $n = fwrite($this->stream, $data);
            if (!$n) { throw new QBrainReadError('connection'); }
            $data = substr($data, $n);
        }
    }
    private function send(string $payload, int $opcode = 1): void {
        $size = strlen($payload);
        if ($size > 16384) { throw new QBrainReadError('response_large'); }
        $head = chr(128 | $opcode).($size < 126 ? chr(128 | $size) : chr(254).pack('n',$size));
        $mask = random_bytes(4); $masked = '';
        for ($i=0; $i<$size; $i++) { $masked .= $payload[$i] ^ $mask[$i%4]; }
        $this->write($head.$mask.$masked);
    }
    private function message(): string {
        $payload = ''; $started = false;
        while (true) {
            $head = $this->read(2); $first = ord($head[0]); $second = ord($head[1]);
            $opcode = $first & 15; $fin = ($first & 128) !== 0;
            if (($first & 112) || ($second & 128)) { throw new QBrainReadError('ws_protocol'); }
            $len = $second & 127;
            if ($len === 126) { $len = unpack('n', $this->read(2))[1]; }
            elseif ($len === 127) { $parts=unpack('Nhi/Nlo', $this->read(8)); if ($parts['hi'] !== 0) { throw new QBrainReadError('response_large'); } $len=$parts['lo']; }
            if ($len > 8388608 || strlen($payload)+$len > 8388608) { throw new QBrainReadError('response_large'); }
            $part = $this->read($len);
            if ($opcode >= 8) {
                if (!$fin || $len > 125) { throw new QBrainReadError('ws_protocol'); }
                if ($opcode === 8) { throw new QBrainReadError('connection'); }
                if ($opcode === 9) { $this->send($part,10); }
                elseif ($opcode !== 10) { throw new QBrainReadError('ws_protocol'); }
                continue;
            }
            if ((!$started && !in_array($opcode,[1,2],true)) || ($started && $opcode !== 0)) { throw new QBrainReadError('ws_protocol'); }
            $started=true; $payload.=$part;
            if ($fin) { return $payload; }
        }
    }
    private function receive(): ?array {
        $message=$this->message();
        if (strlen($message) === 8 && ord($message[0]) === 3) {
            $kind=ord($message[1]);
            if ($kind === 5) { throw new QBrainReadError('connection'); }
            if ($kind === 6) { return null; }
            if (ord($message[2]) & 1) { return null; } // estimated header; exact header follows
            $this->kind=$kind; $this->size=unpack('V',substr($message,4,4))[1];
            if ($this->size > 8388608) { throw new QBrainReadError('response_large'); }
            return null;
        }
        $kind=$this->kind; $size=$this->size; $this->kind=null; $this->size=null;
        if ($size !== null && $size !== strlen($message)) { throw new QBrainReadError('ws_protocol'); }
        if ($kind === 2) {
            if (strlen($message)%24 !== 0) { throw new QBrainReadError('ws_protocol'); }
            for ($i=0; $i<strlen($message); $i+=24) {
                $uuid=unpack('Va/vb/vc',substr($message,$i,8));
                $id=sprintf('%08x-%04x-%04x-', $uuid['a'],$uuid['b'],$uuid['c']).bin2hex(substr($message,$i+8,8));
                $value=unpack('e',substr($message,$i+16,8))[1];
                if (isset($this->wanted[$id]) && is_finite($value)) { $this->values[$id]=$value; }
            }
        } elseif ($kind === 0 || $kind === null) {
            $data=json_decode($message,true);
            if (is_array($data) && is_array($data['LL'] ?? null)) { return $data['LL']; }
        }
        return null;
    }
    public function request(string $command) {
        // No control commands. This private client only authenticates and subscribes to state events.
        if (!preg_match('~^jdev/(?:sys/(?:getkey|getkey2/[^/]+|getjwt/[^/]+/[^/]+/2/[a-f0-9-]{35}/Q-Brain|killtoken/[^/]+/[^/]+)|sps/enablebinstatusupdate)$~D', $command)) {
            throw new QBrainReadError('ws_protocol');
        }
        $this->send($command);
        while (true) {
            $response=$this->receive();
            if ($response !== null) {
                if ((int)($response['Code'] ?? $response['code'] ?? 0) !== 200) { throw new QBrainReadError('ws_authentication'); }
                return $response['value'] ?? null;
            }
        }
    }
    public function collect(): void {
        $until=min($this->deadline-3, microtime(true)+6);
        while (count($this->values) < count($this->wanted) && microtime(true)<$until) {
            try { $this->receive(); } catch (QBrainReadError $e) { if ($e->reason === 'timeout') { break; } throw $e; }
        }
    }
    public function close(): void { if (is_resource($this->stream)) { fclose($this->stream); } }
    public function __destruct() { $this->close(); }
}
function qbrain_socket_values(array $server, array $wanted, string $identity): array {
    $socket=null; $token=null; $user=rawurlencode((string)($server['Admin_RAW'] ?? urldecode($server['Admin'] ?? ''))); $alg='sha256';
    try {
        $socket=new QBrainSocket($server,$wanted);
        $challenge=$socket->request('jdev/sys/getkey2/'.$user);
        $alg=strtolower((string)($challenge['hashAlg'] ?? 'SHA1'));
        if (!in_array($alg,['sha1','sha256'],true) || !ctype_xdigit($challenge['key'] ?? '') || strlen($challenge['key'])%2) { throw new QBrainReadError('ws_protocol'); }
        $password=(string)($server['Pass_RAW'] ?? urldecode($server['Pass'] ?? ''));
        $pwHash=strtoupper(hash($alg,$password.':'.($challenge['salt'] ?? '')));
        $hash=hash_hmac($alg,rawurldecode($user).':'.$pwHash,hex2bin($challenge['key']));
        $hex=substr(hash('sha256',$identity),0,32);
        $uuid=substr($hex,0,8).'-'.substr($hex,8,4).'-'.substr($hex,12,4).'-'.substr($hex,16);
        $auth=$socket->request('jdev/sys/getjwt/'.$hash.'/'.$user.'/2/'.$uuid.'/Q-Brain');
        $token=$auth['token'] ?? null;
        $socket->request('jdev/sps/enablebinstatusupdate');
        $socket->collect();
        return ['values'=>$socket->values,'error'=>null];
    } catch (QBrainReadError $e) { return ['values'=>[], 'error'=>$e->reason]; }
    catch (Throwable $e) { return ['values'=>[], 'error'=>'ws_protocol']; }
    finally {
        if ($socket) {
            if (is_string($token) && $token !== '') {
                try {
                    $key=$socket->request('jdev/sys/getkey');
                    if (is_string($key) && ctype_xdigit($key) && strlen($key)%2===0) {
                        $socket->request('jdev/sys/killtoken/'.hash_hmac($alg,$token,hex2bin($key)).'/'.$user);
                    }
                } catch (Throwable $e) { /* Best effort: permission-2 tokens expire on the Miniserver. */ }
            }
            $socket->close();
        }
    }
}
