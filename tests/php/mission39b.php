<?php
declare(strict_types=1);
require_once __DIR__ . '/guard.php';

function deliver(string $dir, string $content = 'fixture', string $ip = '192.0.2.1',
    int $now = CLOCK, bool $mail = true): array {
    $calls = 0; $reason = null;
    $ok = mamourart_contact_reserve($dir, $ip, static fn(): int => $now, $content,
        static function () use (&$calls, $mail): bool { ++$calls; return $mail; }, $reason);
    return [$ok, $reason, $calls];
}

test('39B exact retry succeeds without sending or consuming either quota, even across IPs', static function (): void {
    $dir = freshLedger();
    same(deliver($dir), [true, 'sent', 1]);
    $snapshot = file_get_contents($dir . '/state.json');
    for ($i = 1; $i <= 10; ++$i) same(deliver($dir, 'fixture', '192.0.2.' . $i), [true, 'already_processed', 0]);
    same(file_get_contents($dir . '/state.json'), $snapshot);
    same(deliver($dir, 'different'), [true, 'sent', 1]);
    same(count(state($dir)), 2);
});
test('39B exact five-minute boundary and expired fingerprint cleanup preserve hourly quota', static function (): void {
    $dir = freshLedger(); same(deliver($dir), [true, 'sent', 1]);
    same(deliver($dir, 'fixture', '192.0.2.1', CLOCK + 299), [true, 'already_processed', 0]);
    same(deliver($dir, 'fixture', '192.0.2.1', CLOCK + 300), [true, 'sent', 1]);
    same(isset(state($dir)[0]['digest']), false);
    same(count(state($dir)), 2);
    same(deliver($dir, 'new', '192.0.2.1', CLOCK + 3600), [true, 'sent', 1]);
    same(count(state($dir)), 2);
    same(isset(state($dir)[0]['digest']), false);
});
test('39B failed mail permits identical retry while preserving conservative quotas', static function (): void {
    $dir = freshLedger(); same(deliver($dir, 'fixture', '192.0.2.1', CLOCK, false), [false, 'mail_failure', 1]);
    same(isset(state($dir)[0]['digest']), false);
    same(deliver($dir), [true, 'sent', 1]);
    same(count(state($dir)), 2);
});
test('39B shared network permits three distinct prospects; other networks retain capacity', static function (): void {
    $dir = freshLedger();
    for ($i = 0; $i < 3; ++$i) same(deliver($dir, 'person' . $i), [true, 'sent', 1]);
    same(deliver($dir, 'person4'), [false, 'individual_quota', 0]);
    for ($i = 0; $i < 5; ++$i) same(deliver($dir, 'other' . $i, '192.0.2.' . ($i + 2)), [true, 'sent', 1]);
    same(deliver($dir, 'ninth', '192.0.2.99'), [false, 'global_quota', 0]);
    same(deliver($dir, 'person0'), [true, 'already_processed', 0]);
    same(count(state($dir)), 8);
});
test('39B legacy reservations still count after keyed bucket migration', static function (): void {
    $dir = freshLedger(); same(reserve($dir, '192.0.2.1'), true);
    same(reserve($dir, '192.0.2.1'), true);
    same(deliver($dir), [true, 'sent', 1]);
    same(deliver($dir, 'distinct'), [false, 'individual_quota', 0]);
});
test('39B key and state private, no raw fixture, email or IP in technical storage', static function (): void {
    $dir = freshLedger(); same(deliver($dir, 'Alice alice@example.test secret description'), [true, 'sent', 1]);
    same(fileperms($dir) & 0777, 0700);
    foreach (['state.json', 'key', 'lock'] as $file) same(fileperms($dir . '/' . $file) & 0777, 0600);
    $raw = file_get_contents($dir . '/state.json');
    foreach (['Alice', 'alice@example.test', '192.0.2.1', 'description'] as $value) check(!str_contains($raw, $value), 'Raw fixture leaked');
    $other = freshLedger(); same(deliver($other, 'Alice alice@example.test secret description'), [true, 'sent', 1]);
    check(state($dir)[0]['digest'] !== state($other)[0]['digest'], 'Independent ledgers correlate');
});
test('39B missing, corrupt and symlinked keys fail closed without mail', static function (): void {
    foreach (['missing', 'corrupt', 'symlink'] as $mode) {
        $dir = freshLedger(); deliver($dir);
        unlink($dir . '/key');
        if ($mode === 'corrupt') file_put_contents($dir . '/key', 'bad');
        if ($mode === 'symlink') symlink($dir . '/state.json', $dir . '/key');
        same(deliver($dir, 'new'), [false, 'storage_failure', 0]);
    }
});
test('39B corrupt fingerprint schema and unavailable storage fail closed', static function (): void {
    foreach ([['digest' => 'invalid', 'sent' => true], ['digest' => str_repeat('a', 64), 'sent' => 'yes']] as $bad) {
        $dir = freshLedger(); deliver($dir);
        $history = state($dir); $history[0] = array_replace($history[0], $bad);
        file_put_contents($dir . '/state.json', json_encode($history));
        same(deliver($dir), [false, 'storage_failure', 0]);
    }
    $file = fresh() . '/blocked'; file_put_contents($file, 'occupied');
    same(deliver($file), [false, 'storage_failure', 0]);
});
test('39B interrupted pending reservation never claims success and expires after five minutes', static function (): void {
    $dir = freshLedger(); deliver($dir);
    $history = state($dir); $history[0]['sent'] = false;
    file_put_contents($dir . '/state.json', json_encode($history));
    same(deliver($dir), [false, 'pending', 0]);
    same(deliver($dir, 'fixture', '192.0.2.1', CLOCK + 300), [true, 'sent', 1]);
    same(count(state($dir)), 2);
});
test('39B endpoint deduplicates and distinguishes every meaningful validated field', static function (): void {
    $temp = fresh();
    $first = endpoint(['temp' => $temp]); redirect($first, 'sent'); same(count($first['mails']), 1);
    $second = endpoint(['temp' => $temp]); redirect($second, 'sent'); same($second['mails'], []);
    foreach (['name' => 'Bob Example', 'company' => 'Other company', 'email' => 'bob@example.test',
        'service' => 'other', 'details' => 'Another valid description with enough characters.'] as $field => $value) {
        $different = endpoint(['temp' => $temp, 'server' => ['REMOTE_ADDR' => '192.0.2.' . (count(glob($temp . '/*')) + ord($field[0]))],
            'post' => [$field => $value]]);
        redirect($different, 'sent'); same(count($different['mails']), 1);
    }
});
test('39B endpoint failed mail can be retried immediately', static function (): void {
    $temp = fresh(); $first = endpoint(['temp' => $temp, 'mail_ok' => false]);
    redirect($first, 'error'); same(count($first['mails']), 1);
    $retry = endpoint(['temp' => $temp]); redirect($retry, 'sent'); same(count($retry['mails']), 1);
});
foreach ([['name' => str_repeat('é', 120), 'company' => str_repeat('界', 120), 'details' => str_repeat('é', 3500)],
    ['name' => str_repeat('😀', 60), 'details' => str_repeat('😀', 1750)],
    ['name' => 'Éà', 'details' => str_repeat('é', 20)], ['company' => '', 'details' => str_repeat('界', 3500)]] as $i => $post) {
    test('39B UTF16 valid boundaries #' . $i, static function () use ($post): void {
        $result = endpoint(['post' => $post, 'server' => ['CONTENT_LENGTH' => '34000']]);
        redirect($result, 'sent'); same(count($result['mails']), 1);
    });
}
foreach ([['name' => str_repeat('é', 121)], ['company' => str_repeat('界', 121)],
    ['details' => str_repeat('😀', 1751)], ['details' => str_repeat('é', 19)],
    ['company' => "\xff"], ['name' => 'É']] as $i => $post) {
    test('39B UTF16 invalid boundaries #' . $i, static function () use ($post): void {
        $result = endpoint(['post' => $post]); redirect($result, 'error'); same($result['mails'], []);
    });
}

test('39B sixteen concurrent identical requests send exactly once and consume one reservation', static function (): void {
    $dir = freshLedger(); $workers = [];
    for ($i = 0; $i < 16; ++$i) {
        $config = fresh() . '/worker.json';
        file_put_contents($config, json_encode(['directory' => $dir, 'ip' => '192.0.2.' . ($i + 1), 'now' => CLOCK, 'content' => 'same request']));
        $process = proc_open([PHP_BINARY, '-n', '-d', 'disable_functions=mail', '-d', 'allow_url_fopen=0', __DIR__ . '/worker.php', $config],
            [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
        check(is_resource($process), 'Cannot create worker'); $workers[] = [$process, $pipes];
    }
    foreach ($workers as [$process, $pipes]) same(fgets($pipes[1]), "ready\n");
    foreach ($workers as [$process, $pipes]) { fwrite($pipes[0], "go\n"); fclose($pipes[0]); }
    $sent = 0;
    foreach ($workers as [$process, $pipes]) {
        $result = json_decode(stream_get_contents($pipes[1]), true);
        same(stream_get_contents($pipes[2]), ''); fclose($pipes[1]); fclose($pipes[2]); same(proc_close($process), 0);
        same($result[0], true); check(in_array($result[1], ['sent', 'already_processed'], true), 'Unexpected concurrent reason');
        if ($result[1] === 'sent') ++$sent;
    }
    same($sent, 1); same(file_get_contents($dir . '/mail-calls'), "stub\n"); same(count(state($dir)), 1);
});


test('39B scheduled maintenance removes expired fingerprints and reservations without reserving quota', static function (): void {
    $dir = freshLedger(); deliver($dir);
    $reason = null;
    same(mamourart_contact_reserve($dir, '', static fn(): int => CLOCK + 300, null, null, $reason, true), true);
    same(count(state($dir)), 1); same(isset(state($dir)[0]['digest']), false);
    unlink($dir . '/key');
    same(deliver($dir, 'new', '192.0.2.1', CLOCK + 301), [false, 'storage_failure', 0]);
    same(mamourart_contact_reserve($dir, '', static fn(): int => CLOCK + 3600, null, null, $reason, true), true);
    same(state($dir), []);
});
test('39B optional diagnostics aggregate only reasons, rotate by day and bound writes', static function (): void {
    $dir = fresh();
    putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR=' . $dir);
    try {
        mamourart_contact_diagnostic('validation');
        $path = $dir . '/observations.json';
        $first = file_get_contents($path);
        mamourart_contact_diagnostic('validation'); same(file_get_contents($path), $first);
        foreach (['honeypot', 'individual_quota', 'global_quota', 'already_processed', 'pending', 'storage_failure', 'mail_failure'] as $reason)
            mamourart_contact_diagnostic($reason);
        $state = json_decode(file_get_contents($path), true);
        same(count($state), 9); same($state['validation']['minutes'], 1);
        same(fileperms($path) & 0777, 0600); check(filesize($path) < 2048, 'Unbounded diagnostics');
        $snapshot = file_get_contents($path);
        mamourart_contact_diagnostic('alice@example.test'); same(file_get_contents($path), $snapshot);
        file_put_contents($path, '{"day":0,"validation":{"minute":0,"minutes":1440}}');
        mamourart_contact_diagnostic('maintenance');
        same(array_keys(json_decode(file_get_contents($path), true)), ['day']);
    } finally { putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR'); }
});
test('39B diagnostics refuse public directories and symlinks; disabled default creates nothing', static function (): void {
    $dir = fresh(); $oldRoot = $_SERVER['DOCUMENT_ROOT'] ?? null;
    $_SERVER['DOCUMENT_ROOT'] = $dir;
    putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR=' . $dir);
    try {
        mamourart_contact_diagnostic('validation'); same(glob($dir . '/*'), []);
        $_SERVER['DOCUMENT_ROOT'] = '/app';
        $target = fresh() . '/unchanged'; file_put_contents($target, 'untouched');
        symlink($target, $dir . '/observations.json');
        mamourart_contact_diagnostic('validation'); same(file_get_contents($target), 'untouched');
    } finally {
        putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR');
        if ($oldRoot === null) unset($_SERVER['DOCUMENT_ROOT']); else $_SERVER['DOCUMENT_ROOT'] = $oldRoot;
    }
    mamourart_contact_diagnostic('validation'); same(file_get_contents($target), 'untouched');
});

test('39B failed completion write retains pending state and never reports success', static function (): void {
    $dir = freshLedger(); deliver($dir, 'first'); $calls = 0; $reason = null;
    $GLOBALS['contact_fault'] = '';
    try {
        $ok = \MamourartContactFaults\mamourart_contact_reserve($dir, '192.0.2.2', static fn(): int => CLOCK,
            'uncertain', static function () use (&$calls): bool {
                ++$calls; $GLOBALS['contact_fault'] = 'snapshot-rename'; return true;
            }, $reason);
        same($ok, false); same($reason, 'storage_failure'); same($calls, 1);
    } finally { $GLOBALS['contact_fault'] = ''; }
    same(deliver($dir, 'uncertain', '192.0.2.2'), [false, 'pending', 0]);
    same(count(state($dir)), 2);
});
test('39B failed admission and key publication never reach mail', static function (): void {
    foreach (['temp', 'open-write', 'write-partial', 'flush', 'rename'] as $fault) {
        $dir = freshLedger(); same(reserve($dir, '192.0.2.1'), true);
        $calls = 0; $reason = null; $before = file_get_contents($dir . '/state.json');
        $GLOBALS['contact_fault'] = $fault; $GLOBALS['contact_partial_written'] = 0;
        try {
            same(\MamourartContactFaults\mamourart_contact_reserve($dir, '192.0.2.2', static fn(): int => CLOCK,
                'fixture', static function () use (&$calls): bool { ++$calls; return true; }, $reason), false);
            same($calls, 0); same($reason, 'storage_failure');
            same(file_get_contents($dir . '/state.json'), $before);
        } finally { $GLOBALS['contact_fault'] = ''; }
        same(deliver($dir), [true, 'sent', 1]);
    }
});
test('39B throwing mail adapter releases lock and permits a legitimate retry', static function (): void {
    $dir = freshLedger(); $reason = null;
    same(mamourart_contact_reserve($dir, '192.0.2.1', static fn(): int => CLOCK, 'fixture',
        static function (): bool { throw new RuntimeException('stub failure'); }, $reason), false);
    same($reason, 'mail_failure'); same(deliver($dir), [true, 'sent', 1]);
});

test('39B browser textarea CRLF transport respects UTF16 limits and canonical retry', static function (): void {
    $temp = fresh();
    $text = str_repeat("é\n", 1749) . 'éa';
    $result = endpoint(['temp' => $temp, 'post' => ['details' => str_replace("\n", "\r\n", $text)]]);
    redirect($result, 'sent'); same(count($result['mails']), 1);
    $retry = endpoint(['temp' => $temp, 'post' => ['details' => $text]]);
    redirect($retry, 'sent'); same($retry['mails'], []);
});
test('39B endpoint emits private diagnostics for rejections, duplicate and mail failures', static function (): void {
    $diag = fresh(); $temp = fresh(); $options = ['temp' => $temp, 'diagnostics_dir' => $diag];
    endpoint($options + ['post' => ['email' => 'invalid']]);
    endpoint($options + ['post' => ['website' => 'bot']]);
    endpoint($options + ['mail_ok' => false]);
    endpoint($options); endpoint($options);
    endpoint($options + ['post' => ['company' => 'another']]);
    endpoint($options + ['post' => ['company' => 'blocked']]);
    endpoint(['temp' => $temp . '/absent/blocked', 'diagnostics_dir' => $diag]);
    $state = json_decode(file_get_contents($diag . '/observations.json'), true);
    foreach (['validation', 'honeypot', 'mail_failure', 'already_processed', 'individual_quota', 'storage_failure'] as $reason)
        check(isset($state[$reason]), 'Missing reason ' . $reason);
    foreach (['Alice', 'alice@example.test', '192.0.2.1', 'A valid request'] as $raw)
        check(!str_contains(file_get_contents($diag . '/observations.json'), $raw), 'Diagnostic fixture leaked');
});
test('39B maintenance prunes bounded stale crash files without touching recent snapshots', static function (): void {
    $dir = freshLedger(); deliver($dir);
    file_put_contents($dir . '/.state-old', 'opaque'); touch($dir . '/.state-old', CLOCK - 3600);
    file_put_contents($dir . '/.state-recent', 'opaque'); touch($dir . '/.state-recent', CLOCK);
    $inode = fileinode($dir . '/lock'); $reason = null;
    same(mamourart_contact_reserve($dir, '', static fn(): int => CLOCK, null, null, $reason, true), true);
    same(file_exists($dir . '/.state-old'), false); same(file_exists($dir . '/.state-recent'), true);
    same(fileinode($dir . '/lock'), $inode); same(count(state($dir)), 1);
});

test('39B concurrent distinct submissions respect keyed individual and global quotas', static function (): void {
    $dir = freshLedger(); $ips = []; $contents = [];
    for ($i = 0; $i < 20; ++$i) { $ips[] = '192.0.2.' . ($i % 4 + 1); $contents[] = 'distinct-' . $i; }
    $allowed = concurrent($dir, $ips, $contents);
    same(count($allowed), 8);
    foreach (array_count_values($allowed) as $count) check($count <= 3, 'Keyed individual quota exceeded');
    same(count(state($dir)), 8); same(substr_count(file_get_contents($dir . '/mail-calls'), "stub\n"), 8);
});
