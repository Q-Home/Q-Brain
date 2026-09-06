<?php
/** CLI-only SDK reader. No URL, credentials or arbitrary command accepted. */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
ini_set('display_errors', '0');
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
        if (!isset($servers[$id])) { throw new RuntimeException('Selecteer een Miniserver uit LoxBerry.'); }
        $deadline = microtime(true) + 20;
        $read = function(string $path) use ($id, $deadline): string {
            if (microtime(true) >= $deadline) { throw new RuntimeException('Leestijd verstreken.'); }
            [$body, $info] = mshttp_call2($id, $path, ['timeout' => 3, 'ssl_verify_mode' => 1, 'ssl_verify_hostname' => 1]);
            if (($info['error'] ?? 1) || ($info['code'] ?? 0) !== 200 || !is_string($body) || strlen($body) > 8388608) {
                throw new RuntimeException('Miniserver niet leesbaar. Controleer bereikbaarheid, certificaat en LoxBerry-accountrechten.');
            }
            return $body;
        };
        $structure = json_decode($read('/data/LoxAPP3.json'), true, 64, JSON_THROW_ON_ERROR);
        $controls = $structure['controls'] ?? [];
        $candidates = [];
        $scan = function(array $items, int $depth = 0) use (&$scan, &$candidates): void {
            if ($depth > 8) { return; }
            foreach ($items as $uuid => $control) {
                if (!is_array($control)) { continue; }
                $name = substr((string)($control['name'] ?? ''), 0, 128);
                if (preg_match('/pv|solar|zonne|batter|accu|soc|grid|net|laad|ev\b|wallbox|charge|photovolta|netz/i', $name)
                    && preg_match('/^[a-f0-9-]{32,36}$/iD', (string)$uuid)) {
                    $candidates[(string)$uuid] = ['id' => (string)$uuid, 'name' => $name,
                        'type' => (string)($control['type'] ?? ''),
                        'format' => substr((string)($control['details']['format'] ?? ''), 0, 64)];
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
            if ($candidate['type'] === 'InfoOnlyAnalog' && $attempts < 20 && microtime(true) < $deadline) {
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
        $result += ['timestamp' => time(), 'miniserver_id' => $id, 'readings' => $readings,
                    'truncated' => count($candidates) > 100, 'error' => null];
    } elseif (($argv[1] ?? '') !== 'list') { throw new RuntimeException('Unknown operation'); }
    ob_end_clean();
    echo json_encode($result, JSON_THROW_ON_ERROR | JSON_INVALID_UTF8_SUBSTITUTE);
} catch (Throwable $e) {
    ob_end_clean();
    echo json_encode(['error' => 'LoxBerry SDK: geen gegevens beschikbaar. Controleer Miniserverselectie, rechten, verbinding en certificaat.']);
    exit(1);
}
