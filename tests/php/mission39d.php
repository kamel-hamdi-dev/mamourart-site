<?php
declare(strict_types=1);
require_once __DIR__ . "/guard.php";

function slowWorker(string $directory, string $mode = 'slow', int $now = CLOCK): array {
    $config = fresh() . '/slow.json';
    file_put_contents($config, json_encode(['directory' => $directory, 'mode' => $mode, 'now' => $now]));
    $process = proc_open([PHP_BINARY, '-n', '-d', 'disable_functions=mail', '-d', 'allow_url_fopen=0', __DIR__ . '/slow-worker.php', $config],
        [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
    check(is_resource($process), 'Cannot start isolated transport worker');
    stream_set_timeout($pipes[1], 5);
    same(fgets($pipes[1]), "transport\n");
    return [$process, $pipes];
}
function finishSlow(array $worker, int $exit = 0): string {
    [$process, $pipes] = $worker;
    if ($exit === 0) { fwrite($pipes[0], "finish\n"); fflush($pipes[0]); }
    fclose($pipes[0]); $output = stream_get_contents($pipes[1]); $errors = stream_get_contents($pipes[2]);
    fclose($pipes[1]); fclose($pipes[2]); same(proc_close($process), $exit); same($errors, '');
    return $output;
}
test('39D slow transport bounds other lock waits, preserves pending and blocks concurrent cleanup', static function (): void {
    $dir = freshLedger(); $worker = slowWorker($dir);
    try {
        foreach (['slow fixture', 'different prospect'] as $content) {
            $start = hrtime(true);
            same(deliver($dir, $content, '192.0.2.2'), [false, 'lock_busy', 0]);
            $elapsed = (hrtime(true) - $start) / 1e9;
            check($elapsed >= .15 && $elapsed < 2, 'Unexpected lock wait: ' . $elapsed);
        }
        $before = file_get_contents($dir . '/state.json'); $reason = null;
        same(mamourart_contact_reserve($dir, '', static fn(): int => CLOCK + 400, null, null, $reason, true), false);
        same($reason, 'lock_busy'); same(file_get_contents($dir . '/state.json'), $before);
        same(state($dir)[0]['sent'], false);
    } finally { same(json_decode(finishSlow($worker), true), [true, 'sent']); }
    same(deliver($dir, 'slow fixture'), [true, 'already_processed', 0]);
    same(deliver($dir, 'different prospect', '192.0.2.2'), [true, 'sent', 1]);
});
foreach (['crash_before' => 77, 'crash_after' => 78] as $mode => $exit) {
    test('39D actual process interruption preserves pending and conservative retry: ' . $mode, static function () use ($mode, $exit): void {
        $dir = freshLedger(); $worker = slowWorker($dir, $mode); same(finishSlow($worker, $exit), '');
        same(state($dir)[0]['sent'], false);
        same(file_exists($dir . '/accepted'), $mode === 'crash_after');
        same(deliver($dir, 'slow fixture'), [false, 'pending', 0]);
        same(deliver($dir, 'slow fixture', '192.0.2.1', CLOCK + 300), [true, 'sent', 1]);
        same(count(state($dir)), 2);
    });
}
test('39D constant-length HMAC key corruption blocks admissions AND maintenance without mutation', static function (): void {
    $dir = freshLedger(); deliver($dir); $before = file_get_contents($dir . '/state.json');
    $key = file_get_contents($dir . '/key'); $damaged = $key; $damaged[0] = chr(ord($damaged[0]) ^ 1);
    file_put_contents($dir . '/key', $damaged); same(strlen($damaged), 32);
    same(deliver($dir), [false, 'key_integrity', 0]);
    $reason = null;
    same(mamourart_contact_reserve($dir, '', static fn(): int => CLOCK + 7200, null, null, $reason, true), false);
    same($reason, 'key_integrity'); same(file_get_contents($dir . '/state.json'), $before);
    file_put_contents($dir . '/key', $key);
    same(deliver($dir), [true, 'already_processed', 0]);
});
test('39D unbound 39B HMAC history requires authorized recovery; legacy SHA migration remains automatic', static function (): void {
    $dir = freshLedger(); deliver($dir); $history = state($dir); unset($history[0]['key_id']);
    file_put_contents($dir . '/state.json', json_encode($history));
    same(deliver($dir), [false, 'key_integrity', 0]);
    $legacy = freshLedger(); reserve($legacy, '192.0.2.1'); reserve($legacy, '192.0.2.1');
    same(deliver($legacy), [true, 'sent', 1]);
    same(deliver($legacy, 'other'), [false, 'individual_quota', 0]);
    foreach (state($legacy) as $entry) check(isset($entry['key_id']), 'Migration lost binding');
});
foreach ([null, '', '0', '100', 'not-a-length', '48001'] as $length) {
    test('39D missing, malformed or inconsistent HTTP length ' . var_export($length, true), static function () use ($length): void {
        $result = endpoint(['server' => ['CONTENT_LENGTH' => $length]]);
        redirect($result, 'error'); same($result['mails'], []); same(glob($result['temp'] . '/*'), []);
    });
}
foreach (['multipart/form-data; boundary=x', 'application/json', '', 'text/plain',
    'application/x-www-form-urlencoded; charset=iso-8859-1'] as $type) {
    test('39D rejects alternate content parser ' . $type, static function () use ($type): void {
        $result = endpoint(['server' => ['CONTENT_TYPE' => $type]]); redirect($result, 'error'); same($result['mails'], []);
    });
}
foreach ([['post' => ['unexpected' => 'value']], ['files' => ['upload' => ['name' => 'fixture.txt']]],
    ['body' => 'name=Alice&name=Bob'], ['body' => 'name%5B%5D=Alice'], ['body' => 'name=%ZZ'],
    ['body' => 'name=Alice'], ['body' => str_repeat('x', 48001)]] as $i => $case) {
    test('39D rejects unexpected, duplicate, malformed or truncated body #' . $i, static function () use ($case): void {
        $result = endpoint($case); redirect($result, 'error'); same($result['mails'], []);
    });
}
test('39D accepts standard URL encoding and explicit UTF8 charset', static function (): void {
    $result = endpoint(['server' => ['CONTENT_TYPE' => 'application/x-www-form-urlencoded; charset=UTF-8']]);
    redirect($result, 'sent'); same(count($result['mails']), 1);
});

function maintenance(string $public, string $temp, ?string $diag = null, int $exit = 0, ?string $script = null): void {
    global $testRoot;
    $previous = getenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR');
    putenv($diag === null ? 'MAMOURART_CONTACT_DIAGNOSTICS_DIR' : 'MAMOURART_CONTACT_DIAGNOSTICS_DIR=' . $diag);
    $process = proc_open([PHP_BINARY, '-n', '-d', 'disable_functions=mail', '-d', 'allow_url_fopen=0',
        '-d', 'sys_temp_dir=' . $temp, $script ?? dirname(__DIR__, 2) . '/scripts/contact-maintenance.php', $public],
        [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
    putenv($previous === false ? 'MAMOURART_CONTACT_DIAGNOSTICS_DIR' : 'MAMOURART_CONTACT_DIAGNOSTICS_DIR=' . $previous);
    check(is_resource($process), 'Cannot start CLI maintenance'); fclose($pipes[0]);
    same(stream_get_contents($pipes[1]), ''); same(stream_get_contents($pipes[2]), '');
    fclose($pipes[1]); fclose($pipes[2]); same(proc_close($process), $exit);
}
function maintenanceFixture(): array {
    global $fixtures;
    $public = $fixtures['public']; $temp = fresh();
    return [$public, $temp, $temp . '/mamourart-contact-v2-' . substr(hash('sha256', $public), 0, 16)];
}
test('39D actual maintenance CLI clears idle data and reports diagnostic repair as partial', static function (): void {
    [$public, $temp, $dir] = maintenanceFixture(); deliver($dir, 'expired', '192.0.2.1', time() - 4000);
    $diag = fresh(); file_put_contents($diag . '/observations.json', '{broken');
    maintenance($public, $temp, $diag, 3);
    same(state($dir), []); same(array_keys(json_decode(file_get_contents($diag . '/observations.json'), true)), ['day']);
    maintenance($public, $temp, $diag);
    check(is_file($dir . '/key') && is_file($dir . '/lock'), 'CLI removed permanent files');
});
test('39D actual CLI returns errors for storage, usage and unsafe diagnostic path', static function (): void {
    [$public, $temp, $dir] = maintenanceFixture(); maintenance($public, $temp);
    same(file_exists($dir), false);
    file_put_contents($dir, 'blocked'); maintenance($public, $temp, null, 1);
    maintenance(fresh(), $temp, null, 2);
    [$public, $temp, $dir] = maintenanceFixture(); maintenance($public, $temp, $public, 1);
});
test('39D actual CLI reports bounded backlog as partial without deleting foreign or recent files', static function (): void {
    [$public, $temp, $dir] = maintenanceFixture(); deliver($dir, 'fixture', '192.0.2.1', time());
    for ($i = 0; $i < 70; ++$i) file_put_contents($dir . '/foreign-' . $i, 'unchanged');
    file_put_contents($dir . '/.state-foreign-app', 'unchanged'); touch($dir . '/.state-foreign-app', time() - 7200);
    maintenance($public, $temp, null, 3);
    same(count(glob($dir . '/foreign-*')), 70); same(file_get_contents($dir . '/.state-foreign-app'), 'unchanged');
});
foreach (['', '{broken', str_repeat('x', 4096), '{"day":0,"validation":"broken"}'] as $i => $invalid) {
    test('39D diagnostics reject corruption and repair it explicitly in maintenance #' . $i, static function () use ($invalid): void {
        $dir = fresh(); putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR=' . $dir);
        $path = $dir . '/observations.json'; file_put_contents($path, $invalid);
        try {
            same(mamourart_contact_diagnostic('validation'), 'error'); same(file_get_contents($path), $invalid);
            same(mamourart_contact_diagnostic('maintenance'), 'partial');
            same(mamourart_contact_diagnostic('validation'), 'ok'); check(filesize($path) < 2048, 'Diagnostic overflow');
        } finally { putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR'); }
    });
}

test('39D cleanup deletion failure is partial and retry preserves lock and key', static function (): void {
    $dir = freshLedger(); deliver($dir); $reason = null;
    file_put_contents($dir . '/.state-ABC123', 'opaque'); touch($dir . '/.state-ABC123', CLOCK - 7200);
    $GLOBALS['contact_fault'] = 'unlink';
    try {
        same(\MamourartContactFaults\mamourart_contact_reserve($dir, '', static fn(): int => CLOCK, null, null, $reason, true), true);
        same($reason, 'maintenance_partial'); same(file_exists($dir . '/.state-ABC123'), true);
    } finally { $GLOBALS['contact_fault'] = ''; }
    same(mamourart_contact_reserve($dir, '', static fn(): int => CLOCK, null, null, $reason, true), true);
    same($reason, 'maintenance'); same(file_exists($dir . '/.state-ABC123'), false);
    same(deliver($dir), [true, 'already_processed', 0]);
});
test('39D diagnostic read, write, truncate and flush failures are observable', static function (): void {
    foreach (['read', 'write', 'truncate', 'flush', 'lock'] as $fault) {
        $dir = fresh(); putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR=' . $dir);
        $GLOBALS['contact_fault'] = $fault;
        try { same(\MamourartContactFaults\mamourart_contact_diagnostic('validation'), 'error'); }
        finally { $GLOBALS['contact_fault'] = ''; putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR'); }
    }
});

test('39D maintenance rejects simulated HTTP SAPI before any filesystem operation', static function (): void {
    $script = fresh() . '/http-maintenance.php';
    namespaceCopy(dirname(__DIR__, 2) . '/scripts/contact-maintenance.php', $script, 'MamourartContactTests');
    $result = endpoint(['endpoint' => $script, 'sapi' => 'fpm-fcgi']);
    same($result['status'], 404); same($result['mails'], []); same(glob($result['temp'] . '/*'), []);
});
test('39D finalization delayed beyond dedup window cannot race maintenance or lose the reservation', static function (): void {
    $dir = freshLedger(); $worker = slowWorker($dir, 'slow', CLOCK - 400);
    try {
        $reason = null;
        same(mamourart_contact_reserve($dir, '', static fn(): int => CLOCK, null, null, $reason, true), false);
        same($reason, 'lock_busy'); same(state($dir)[0]['sent'], false);
    } finally { same(json_decode(finishSlow($worker), true), [true, 'sent']); }
    same(count(state($dir)), 1); same(state($dir)[0]['sent'], true);
});

test('39D CLI program propagates failed deletion to partial exit status (namespaced fault copy)', static function (): void {
    $public = fresh(); $temp = fresh();
    copy(dirname(__DIR__, 2) . '/contact-submit.php', $public . '/contact-submit.php');
    namespaceCopy(dirname(__DIR__, 2) . '/contact-rate-limit.php', $public . '/contact-rate-limit.php', 'MamourartContactFaults');
    $dir = $temp . '/mamourart-contact-v2-' . substr(hash('sha256', $public), 0, 16);
    deliver($dir, 'fixture', '192.0.2.1', time());
    file_put_contents($dir . '/.state-ABC123', 'opaque'); touch($dir . '/.state-ABC123', time() - 7200);
    $script = fresh() . '/maintenance-fault.php';
    namespaceCopy(dirname(__DIR__, 2) . '/scripts/contact-maintenance.php', $script, 'MamourartContactFaults');
    $source = file_get_contents($script);
    $source = str_replace('use \\Throwable;', 'use \\Throwable;' . "\nrequire " . var_export(__DIR__ . '/guard.php', true) . ";\nrequire " .
        var_export(__DIR__ . '/fault-functions.php', true) . ";\n\$GLOBALS['contact_fault'] = 'unlink';", $source);
    file_put_contents($script, $source);
    maintenance($public, $temp, null, 3, $script);
    same(file_exists($dir . '/.state-ABC123'), true); same(count(state($dir)), 1);
    check(is_file($dir . '/key') && is_file($dir . '/lock'), 'Permanent storage changed');
});
