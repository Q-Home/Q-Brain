<?php
declare(strict_types=1);
require_once 'loxberry_system.php';
require_once 'loxberry_web.php';
require_once 'loxberry_log.php';

// This file is installed only in htmlauth, behind LoxBerry authentication.
session_name('qbrain_session');
session_start(['cookie_httponly' => true, 'cookie_samesite' => 'Strict',
               'cookie_secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
               'use_strict_mode' => true]);
if (empty($_SESSION['qbrain_csrf'])) {
    $_SESSION['qbrain_csrf'] = bin2hex(random_bytes(32));
}
$csrf = $_SESSION['qbrain_csrf'];
session_write_close();
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

function qbrain_call(string $action, ?array $payload = null): array {
    global $lbpconfigdir;
    $allowed = ['config', 'save', 'status', 'start', 'stop', 'pull', 'logs', 'chat'];
    $folder = basename($lbpconfigdir);
    if (!in_array($action, $allowed, true) || !preg_match('/^[A-Za-z0-9_-]+$/D', $folder)) {
        throw new RuntimeException('Ongeldige bewerking.');
    }
    $command = ['/usr/bin/sudo', '-n', '/usr/local/lib/qbrain/' . $folder . '/control.py', $action];
    $pipes = [];
    $process = proc_open($command, [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['file', '/dev/null', 'a']], $pipes);
    if (!is_resource($process)) {
        throw new RuntimeException('De plugincontroller is niet beschikbaar.');
    }
    if ($payload !== null) {
        fwrite($pipes[0], json_encode($payload, JSON_THROW_ON_ERROR));
    }
    fclose($pipes[0]);
    stream_set_timeout($pipes[1], 40);
    $output = stream_get_contents($pipes[1], 524288);
    $timedOut = stream_get_meta_data($pipes[1])['timed_out'];
    fclose($pipes[1]);
    if ($timedOut) {
        proc_terminate($process);
    }
    $code = proc_close($process);
    $result = json_decode($output ?: '', true);
    if (!is_array($result)) {
        throw new RuntimeException('Controller niet bereikbaar. Controleer de installatie en sudo-rechten.');
    }
    if ($code !== 0 || isset($result['error'])) {
        throw new RuntimeException($result['error'] ?? 'Bewerking mislukt.');
    }
    return $result;
}

$action = $_GET['action'] ?? '';
if ($action !== '') {
    header('Content-Type: application/json; charset=utf-8');
    try {
        if (!is_string($action) || !in_array($action, ['config', 'status', 'logs', 'save', 'start', 'stop', 'pull', 'chat'], true)) {
            http_response_code(400);
            throw new RuntimeException('Onbekende bewerking.');
        }
        $mutating = in_array($action, ['save', 'start', 'stop', 'pull', 'chat'], true);
        if ($mutating && ($_SERVER['REQUEST_METHOD'] !== 'POST' ||
                !hash_equals($csrf, $_SERVER['HTTP_X_QBRAIN_CSRF'] ?? ''))) {
            http_response_code(403);
            throw new RuntimeException('Ongeldig formulier. Herlaad de pagina.');
        }
        $payload = null;
        if ($action === 'save' || $action === 'chat') {
            $raw = file_get_contents('php://input', false, null, 0, 32769);
            if (strlen($raw) > 32768) {
                throw new RuntimeException('Configuratie is te groot.');
            }
            $payload = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
            if (!is_array($payload)) {
                throw new RuntimeException('Ongeldige configuratie.');
            }
        }
        $result = qbrain_call($action, $payload);
        if ($mutating && $action !== 'chat') {
            // Only operation names are logged: never payloads, passwords or tokens.
            $log = LBLog::newLog(['name' => 'qbrain-ui', 'addtime' => 1]);
            $log->LOGSTART('Q-Brain');
            $log->INF('Accepted operation: ' . $action);
            $log->LOGEND('Request completed');
        }
        echo json_encode($result, JSON_THROW_ON_ERROR);
    } catch (Throwable $error) {
        if (http_response_code() < 400) {
            http_response_code(400);
        }
        echo json_encode(['error' => $error->getMessage()]);
    }
    exit;
}

$navbar[10] = ['Name' => 'Q-Brain', 'URL' => 'index.php', 'active' => true];
LBWeb::lbheader('Q-Brain', 'https://github.com/Q-Home/Q-Brain', 'help.html', true);
include $lbptemplatedir . '/index.php';
LBWeb::lbfooter();
