<?php
/** CLI-only SDK reader. No URL, credentials or arbitrary command accepted. */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
ini_set('display_errors', '0');
// Compatibility reader for LoxBerry 4.0.0, whose PHP SDK has no mshttp_call2.
// Connection data still comes exclusively from LBSystem::get_miniservers().
class QBrainReadError extends RuntimeException {
    public string $reason;
    public function __construct(string $reason) { $this->reason = $reason; parent::__construct('Q-Brain read failed'); }
}
function qbrain_http_read(array $server, string $path): array {
    if (!preg_match('~^/(?:data/LoxAPP3\.json|dev/sps/io/[a-f0-9-]{32,36}(?:/all)?)$~iD', $path)) {
        throw new QBrainReadError('sdk_unavailable');
    }
    if (!function_exists('curl_init')) { throw new QBrainReadError('php_curl_missing'); }
    $origin = (string)($server['FullURI'] ?? '');
    if (!preg_match('~^https?://~D', $origin)) { throw new QBrainReadError('connection'); }
    $body = ''; $large = false;
    $curl = curl_init($origin . $path);
    curl_setopt_array($curl, [CURLOPT_HEADER => false, CURLOPT_FOLLOWLOCATION => false,
        CURLOPT_CONNECTTIMEOUT => 3, CURLOPT_TIMEOUT => 3,
        CURLOPT_PROTOCOLS => CURLPROTO_HTTP | CURLPROTO_HTTPS,
        CURLOPT_SSL_VERIFYPEER => false, CURLOPT_SSL_VERIFYHOST => 0,
        CURLOPT_WRITEFUNCTION => function($handle, string $chunk) use (&$body, &$large): int {
            if (strlen($body) + strlen($chunk) > 8388608) { $large = true; return 0; }
            $body .= $chunk; return strlen($chunk);
        }]);
    $ok = curl_exec($curl);
    $code = (int)curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $errno = curl_errno($curl);
    curl_close($curl);
    return [$body, ['code' => $code, 'error' => $ok === false ? 1 : 0,
                   'errno' => $errno, 'large' => $large]];
}
function qbrain_check_response($body, array $info): string {
    $code = (int)($info['code'] ?? 0);
    $errno = (int)($info['errno'] ?? 0);
    if (!empty($info['large']) || (is_string($body) && strlen($body) > 8388608)) { throw new QBrainReadError('response_large'); }
    if (in_array($code, [401,403], true)) { throw new QBrainReadError('authentication'); }
    // Native SDK lacks a curl errno field; classify its status without exposing raw text.
    $status = (string)($info['status'] ?? '');
    if (in_array($errno, [51,58,60,77,83,90,91], true) || preg_match('/certificate|SSL peer/i', $status)) { throw new QBrainReadError('certificate'); }
    if ($errno === 28 || preg_match('/timed? ?out|timeout/i', $status)) { throw new QBrainReadError('timeout'); }
    if ($code === 0 || $errno !== 0) { throw new QBrainReadError('connection'); }
    if ($code !== 200 || !empty($info['error']) || !is_string($body)) { throw new QBrainReadError('http_error'); }
    return $body;
}
ob_start();
try {
    $installation = json_decode(file_get_contents(__DIR__ . '/installation.json'), true, 16, JSON_THROW_ON_ERROR);
    $home = $installation['home'];
    putenv('LBHOMEDIR=' . $home);
    set_include_path($home . '/libs/phplib' . PATH_SEPARATOR . get_include_path());
    require_once 'loxberry_system.php';
    require_once 'loxberry_io.php';
    $servers = LBSystem::get_miniservers();
    $list = [];
    foreach ($servers as $id => $server) {
        $list[] = ['id' => (string)$id, 'name' => substr((string)$server['Name'], 0, 128)];
    }
    $result = ['miniservers' => $list];
    if (($argv[1] ?? '') === 'collect') {
        $id = $argv[2] ?? '';
        if ($id === '' && count($list) === 1) { $id = $list[0]['id']; }
        if ($id === '' && count($list) > 1) { throw new QBrainReadError('selection_required'); }
        if (!isset($servers[$id])) { throw new QBrainReadError('miniserver_missing'); }
        if (!function_exists('simplexml_load_string')) { throw new QBrainReadError('php_xml_missing'); }
        $deadline = microtime(true) + 20;
        $read = function(string $path) use ($id, $deadline, $servers): string {
            if (microtime(true) >= $deadline) { throw new QBrainReadError('timeout'); }
            if (function_exists('mshttp_call2')) {
                [$body, $info] = mshttp_call2($id, $path, ['timeout' => 3, 'ssl_verify_mode' => 0, 'ssl_verify_hostname' => 0]);
            } else {
                [$body, $info] = qbrain_http_read($servers[$id], $path);
            }
            return qbrain_check_response($body, $info);
        };
        $rawStructure = $read('/data/LoxAPP3.json');
        try { $structure = json_decode($rawStructure, true, 64, JSON_THROW_ON_ERROR); }
        catch (JsonException $e) { throw new QBrainReadError('structure_invalid'); }
        if (!is_array($structure) || !is_array($structure['controls'] ?? null)) { throw new QBrainReadError('structure_invalid'); }
        $controls = $structure['controls'] ?? [];
        $candidates = [];
        $scan = function(array $items, int $depth = 0) use (&$scan, &$candidates, $structure): void {
            if ($depth > 8) { return; }
            foreach ($items as $uuid => $control) {
                if (!is_array($control)) { continue; }
                $name = substr((string)($control['name'] ?? ''), 0, 128);
                if ((in_array($control['type'] ?? '', ['Meter','Wallbox2','EnergyManager2','InfoOnlyAnalog'], true) || preg_match('/pv|solar|zonne|batter|accu|soc|grid|net|laad|ev\b|wallbox|charge|photovolta|netz/i', $name))
                    && preg_match('/^[a-f0-9-]{32,36}$/iD', (string)$uuid)) {
                    $candidates[(string)$uuid] = ['id' => (string)$uuid, 'name' => $name,
                        'type' => substr((string)($control['type'] ?? ''),0,64),
                        'format' => substr((string)($control['details']['actualFormat'] ?? $control['details']['format'] ?? ''), 0, 64),
                        'room' => substr((string)($structure['rooms'][$control['room'] ?? '']['name'] ?? ''),0,64),
                        'category' => substr((string)($structure['cats'][$control['cat'] ?? '']['name'] ?? ''),0,64),
                        'states' => [], 'details' => []];
                    foreach (['actual','total','storage','value','position','active','connected','enabled','Gpwr','Spwr','Ppwr','Ssoc'] as $field) {
                        $state=$control['states'][$field] ?? null;
                        if (is_string($state) && preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{16}$/iD',$state)) {
                            $candidates[(string)$uuid]['states'][$field]=strtolower($state);
                        }
                    }
                    foreach (['type','actualFormat','totalFormat','storageFormat','storageMax','format','min','max','connectedInputs','HasSsoc','HasSpwr'] as $field) {
                        $detail=$control['details'][$field] ?? null;
                        if (is_string($detail)) { $candidates[(string)$uuid]['details'][$field]=substr($detail,0,128); }
                        elseif (is_bool($detail) || is_numeric($detail)) { $candidates[(string)$uuid]['details'][$field]=$detail; }
                    }
                }
                if (is_array($control['subControls'] ?? null)) { $scan($control['subControls'], $depth + 1); }
            }
        };
        $scan($controls);
        $readings = [];
        $attempts = 0;
        foreach (array_slice($candidates, 0, 100) as $candidate) {
            $candidate['value'] = null;
            $candidate['status'] = 'unsupported_control';
            // Only a scalar read-only analogue display is supported by this first reader.
            // Function-block state UUIDs are NOT treated as HTTP input/output UUIDs.
            if ($candidate['type'] === 'InfoOnlyAnalog' && !$candidate['states'] && $attempts < 20 && microtime(true) < $deadline) {
                $attempts++;
                try {
                    $raw = $read('/dev/sps/io/' . $candidate['id'] . '/all');
                    if (stripos($raw, '<!DOCTYPE') !== false) { throw new RuntimeException('Invalid XML'); }
                    $xml = simplexml_load_string($raw, 'SimpleXMLElement', LIBXML_NONET | LIBXML_NOERROR | LIBXML_NOWARNING);
                    if (!$xml || $xml->getName() !== 'LL' || (string)$xml['Code'] !== '200') { throw new RuntimeException('Invalid response'); }
                    $outputs = $xml->xpath('.//output');
                    if ($outputs) { throw new RuntimeException('Not a scalar input/output'); }
                    $value = (string)$xml['value'];
                    // SDK mshttp_get uses the command-free getter for analogue /all=0.
                    if (is_numeric($value) && (float)$value === 0.0) {
                        $raw = $read('/dev/sps/io/' . $candidate['id']);
                        if (stripos($raw, '<!DOCTYPE') !== false) { throw new RuntimeException('Invalid XML'); }
                        $xml = simplexml_load_string($raw, 'SimpleXMLElement', LIBXML_NONET | LIBXML_NOERROR | LIBXML_NOWARNING);
                        if (!$xml || $xml->getName() !== 'LL' || (string)$xml['Code'] !== '200' || $xml->xpath('.//output')) { throw new RuntimeException('Invalid response'); }
                        $value = (string)$xml['value'];
                    }
                    if (!is_numeric($value) || !is_finite((float)$value)) { throw new RuntimeException('Not numeric'); }
                    $candidate['value'] = (float)$value;
                    $candidate['status'] = 'read';
                } catch (Throwable $e) { $candidate['status'] = 'unreadable'; }
            }
            $readings[] = $candidate;
        }
        $wanted=[];
        foreach ($readings as $reading) { foreach ($reading['states'] as $uuid) { $wanted[$uuid]=true; } }
        $ws=['values'=>[], 'error'=>null];
        if ($wanted) {
            require_once __DIR__.'/loxberry_ws.php';
            $ws=qbrain_socket_values($servers[$id],array_keys($wanted),gethostname().$home.($installation['folder'] ?? 'qbrain'));
        }
        foreach ($readings as &$reading) {
            $reading['state_values']=[];
            foreach ($reading['states'] as $field=>$uuid) { $reading['state_values'][$field]=$ws['values'][$uuid] ?? null; }
            if ($reading['states']) {
                $field=in_array($reading['type'],['Meter','Wallbox2'],true) ? 'actual' : ($reading['type']==='Slider' ? 'position' : 'value');
                $reading['value']=$reading['state_values'][$field] ?? null;
                $reading['status']=count(array_filter($reading['state_values'],fn($v)=>$v!==null)) ? 'read' : 'state_missing';
            }
        }
        unset($reading);
        $result += ['websocket'=>['error'=>$ws['error']], 'timestamp' => time(), 'miniserver_id' => $id, 'readings' => $readings,
                    'truncated' => count($candidates) > 100, 'error' => null];
    } elseif (($argv[1] ?? '') !== 'list') { throw new RuntimeException('Unknown operation'); }
    ob_end_clean();
    echo json_encode($result, JSON_THROW_ON_ERROR | JSON_INVALID_UTF8_SUBSTITUTE);
} catch (Throwable $e) {
    ob_end_clean();
    echo json_encode(['error' => 'SDK read failed', 'error_code' => $e instanceof QBrainReadError ? $e->reason : 'sdk_unavailable']);
    exit(1);
}
