<?php
declare(strict_types=1);
require __DIR__ . '/guard.php';
require dirname(__DIR__, 2) . '/contact-rate-limit.php';

const CLOCK = 1700000000;
$testRoot = sys_get_temp_dir() . '/mamourart-m28-tests-' . bin2hex(random_bytes(12));
if (!mkdir($testRoot, 0700)) throw new RuntimeException('Cannot create isolated test root');
$passed = 0;
$failed = 0;

function removeTree(string $path): void {
    if (is_link($path) || !is_dir($path)) { unlink($path); return; }
    foreach (array_diff(scandir($path), ['.', '..']) as $name) removeTree($path . '/' . $name);
    rmdir($path);
}
register_shutdown_function(static function () use ($testRoot): void { removeTree($testRoot); });
function fresh(): string {
    global $testRoot;
    $directory = $testRoot . '/case-' . bin2hex(random_bytes(8));
    mkdir($directory, 0700);
    return $directory;
}
function freshLedger(): string { return fresh() . '/ledger'; }
function same(mixed $actual, mixed $expected, string $message = ''): void {
    if ($actual !== $expected) throw new RuntimeException($message . ' expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
}
function check(bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
}
function test(string $name, callable $body): void {
    global $passed, $failed;
    try { $body(); ++$passed; echo "PASS $name\n"; }
    catch (Throwable $error) { ++$failed; echo "FAIL $name: " . $error->getMessage() . "\n"; }
}
function reserve(string $directory, string $ip, int $now = CLOCK): bool {
    return mamourart_contact_reserve($directory, $ip, static fn(): int => $now);
}
function state(string $directory): array {
    return json_decode(file_get_contents($directory . '/state.json'), true, 512, JSON_THROW_ON_ERROR);
}
function namespaceCopy(string $source, string $destination, string $namespace): void {
    $code = str_replace('declare(strict_types=1);', "declare(strict_types=1);\nnamespace $namespace;\nuse \\Throwable;", file_get_contents($source), $count);
    same($count, 1, 'Expected exactly one strict declaration in application source');
    file_put_contents($destination, $code);
}
function runChild(string $script, array $arguments = [], ?string $input = null, int $expectedExit = 0): string {
    $process = proc_open([PHP_BINARY, '-n', '-d', 'disable_functions=mail', '-d', 'allow_url_fopen=0', $script, ...$arguments],
        [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
    check(is_resource($process), 'Cannot start PHP child');
    if ($input !== null) fwrite($pipes[0], $input);
    fclose($pipes[0]);
    $output = stream_get_contents($pipes[1]);
    $errors = stream_get_contents($pipes[2]);
    fclose($pipes[1]); fclose($pipes[2]);
    same(proc_close($process), $expectedExit, 'PHP child failed: ' . $errors . $output);
    same($errors, '', 'Unexpected child stderr');
    return $output;
}
function concurrent(string $directory, array $ips, ?array $contents = null): array {
    $workers = [];
    foreach ($ips as $i => $ip) {
        $configuration = fresh() . '/worker.json';
        $config = ['directory' => $directory, 'ip' => $ip, 'now' => CLOCK];
        if ($contents !== null) $config['content'] = $contents[$i];
        file_put_contents($configuration, json_encode($config, JSON_THROW_ON_ERROR));
        $process = proc_open([PHP_BINARY, '-n', '-d', 'disable_functions=mail', '-d', 'allow_url_fopen=0', __DIR__ . '/worker.php', $configuration],
            [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
        check(is_resource($process), 'Cannot start concurrent worker');
        stream_set_timeout($pipes[1], 15);
        $workers[] = [$process, $pipes];
    }
    // Every worker has reached the barrier before any reservation may begin.
    foreach ($workers as [$process, $pipes]) same(fgets($pipes[1]), "ready\n", 'Worker did not reach barrier');
    foreach ($workers as [$process, $pipes]) { fwrite($pipes[0], "go\n"); fclose($pipes[0]); }
    $allowed = [];
    foreach ($workers as $index => [$process, $pipes]) {
        $output = stream_get_contents($pipes[1]); $errors = stream_get_contents($pipes[2]);
        fclose($pipes[1]); fclose($pipes[2]);
        same(proc_close($process), 0, 'Concurrent worker failed: ' . $errors);
        same($errors, '', 'Concurrent worker stderr');
        if ($contents !== null) $output = json_decode($output, true)[0] ? "1\n" : "0\n";
        check(in_array($output, ["0\n", "1\n"], true), 'Invalid worker result: ' . $output);
        if ($output === "1\n") $allowed[] = $ips[$index];
    }
    return $allowed;
}

test('IP refusals preserve global capacity; other visitors fill remaining five slots', static function (): void {
    $dir = freshLedger();
    for ($i = 0; $i < 3; ++$i) same(reserve($dir, '192.0.2.1'), true);
    $before = file_get_contents($dir . '/state.json');
    for ($i = 0; $i < 5; ++$i) same(reserve($dir, '192.0.2.1'), false);
    same(file_get_contents($dir . '/state.json'), $before, 'IP refusal mutated counters');
    for ($i = 0; $i < 3; ++$i) same(reserve($dir, '192.0.2.2'), true);
    for ($i = 0; $i < 2; ++$i) same(reserve($dir, '192.0.2.3'), true);
    same(count(state($dir)), 8);
    $full = file_get_contents($dir . '/state.json');
    same(reserve($dir, '192.0.2.4'), false);
    same(file_get_contents($dir . '/state.json'), $full, 'Global refusal mutated counters');
});
test('Global rejection does not consume IP quota in the next second', static function (): void {
    $dir = freshLedger();
    for ($i = 1; $i <= 8; ++$i) same(reserve($dir, '192.0.2.' . $i), true);
    for ($i = 0; $i < 5; ++$i) same(reserve($dir, '198.51.100.1', CLOCK + 3599), false);
    for ($i = 0; $i < 3; ++$i) same(reserve($dir, '198.51.100.1', CLOCK + 3600), true);
    same(reserve($dir, '198.51.100.1', CLOCK + 3600), false);
});
test('One-hour expiration is exact for both quotas', static function (): void {
    $dir = freshLedger();
    for ($i = 0; $i < 3; ++$i) same(reserve($dir, '2001:db8::1'), true);
    same(reserve($dir, '2001:db8::1', CLOCK + 3599), false);
    same(reserve($dir, '2001:db8::1', CLOCK + 3600), true);
    same(count(state($dir)), 1);
    same(state($dir)[0]['time'], CLOCK + 3600);
});
test('Staggered reservations expire individually', static function (): void {
    $dir = freshLedger();
    same(reserve($dir, '192.0.2.1'), true);
    same(reserve($dir, '192.0.2.1', CLOCK + 1), true);
    same(reserve($dir, '192.0.2.1', CLOCK + 2), true);
    same(reserve($dir, '192.0.2.1', CLOCK + 3600), true);
    same(count(state($dir)), 3);
    same(reserve($dir, '192.0.2.1', CLOCK + 3600), false);
    same(reserve($dir, '192.0.2.1', CLOCK + 3601), true);
});
test('Clock rollback retains future reservations conservatively', static function (): void {
    $dir = freshLedger();
    for ($i = 0; $i < 3; ++$i) same(reserve($dir, '192.0.2.1'), true);
    $snapshot = file_get_contents($dir . '/state.json');
    same(reserve($dir, '192.0.2.1', CLOCK - 3601), false);
    same(file_get_contents($dir . '/state.json'), $snapshot);
    same(reserve($dir, '192.0.2.1', CLOCK), false);
    same(reserve($dir, '192.0.2.1', CLOCK + 3600), true);
});
test('Forward clock jump expires quotas; subsequent rollback fails closed without mutation', static function (): void {
    $dir = freshLedger();
    for ($i = 0; $i < 3; ++$i) same(reserve($dir, '192.0.2.1'), true);
    same(reserve($dir, '192.0.2.1', CLOCK + 7200), true);
    $snapshot = file_get_contents($dir . '/state.json');
    same(reserve($dir, '192.0.2.2', CLOCK + 3600), false);
    same(file_get_contents($dir . '/state.json'), $snapshot);
    same(reserve($dir, '192.0.2.2', CLOCK + 7200), true);
});
foreach ([-1, '1700000000', 1700000000.0, null, true] as $index => $badClock) {
    test('Invalid clock callback fails closed and preserves ledger #' . $index, static function () use ($badClock): void {
        $dir = freshLedger(); same(reserve($dir, '192.0.2.1'), true);
        $snapshot = file_get_contents($dir . '/state.json');
        same(mamourart_contact_reserve($dir, '192.0.2.2', static fn(): mixed => $badClock), false);
        same(file_get_contents($dir . '/state.json'), $snapshot);
        same(reserve($dir, '192.0.2.2'), true);
    });
}
test('Throwing clock callback fails closed and releases lock', static function (): void {
    $dir = freshLedger(); same(reserve($dir, '192.0.2.1'), true);
    $snapshot = file_get_contents($dir . '/state.json');
    same(mamourart_contact_reserve($dir, '192.0.2.2', static function (): never { throw new RuntimeException('clock failed'); }), false);
    same(file_get_contents($dir . '/state.json'), $snapshot);
    same(reserve($dir, '192.0.2.2'), true);
});
test('State contains only timestamps and opaque IP buckets', static function (): void {
    $dir = freshLedger(); same(reserve($dir, '192.0.2.99'), true);
    same(state($dir), [['time' => CLOCK, 'bucket' => substr(hash('sha256', 'mamourart-contact-v1|192.0.2.99'), 0, 32)]]);
    check(!str_contains(file_get_contents($dir . '/state.json'), '192.0.2.99'), 'Raw IP leaked');
});
test('Missing storage directory is initialized privately', static function (): void {
    $dir = fresh() . '/not-created';
    same(reserve($dir, '192.0.2.1'), true);
    same(fileperms($dir) & 0777, 0700);
    same(count(state($dir)), 1);
});
test('Concurrent same-IP requests allow exactly three reservations', static function (): void {
    $dir = fresh() . '/new-state';
    same(reserve($dir, '198.51.100.254', CLOCK - 3600), true);
    same(count(concurrent($dir, array_fill(0, 16, '192.0.2.1'))), 3);
    same(count(state($dir)), 3);
});
test('Concurrent distinct-IP requests allow exactly eight reservations', static function (): void {
    $dir = fresh() . '/new-state';
    same(reserve($dir, '198.51.100.254', CLOCK - 3600), true);
    $ips = array_map(static fn(int $i): string => '192.0.2.' . $i, range(1, 20));
    same(count(concurrent($dir, $ips)), 8);
    same(count(state($dir)), 8);
});
test('Concurrent mixed-IP requests respect both quotas', static function (): void {
    $dir = freshLedger();
    same(reserve($dir, '198.51.100.254', CLOCK - 3600), true);
    $ips = [];
    for ($i = 0; $i < 6; ++$i) foreach (['192.0.2.1', '192.0.2.2', '192.0.2.3'] as $ip) $ips[] = $ip;
    $allowed = concurrent($dir, $ips);
    same(count($allowed), 8);
    foreach (array_count_values($allowed) as $count) check($count <= 3, 'Concurrent IP quota exceeded');
    same(count(state($dir)), 8);
});
test('Concurrent first initialization never exceeds either quota', static function (): void {
    $dir = fresh() . '/cold-start';
    $allowed = concurrent($dir, array_fill(0, 16, '192.0.2.1'));
    same(count($allowed), 3, 'Cold-start lost capacity or exceeded its quota');
    same(count(state($dir)), count($allowed));
});
test('Unavailable storage directory fails closed', static function (): void {
    $path = fresh() . '/not-a-directory'; file_put_contents($path, 'occupied');
    same(reserve($path, '192.0.2.1'), false);
    same(file_get_contents($path), 'occupied');
});
test('Unopenable lock fails closed', static function (): void {
    $dir = fresh(); mkdir($dir . '/lock');
    same(reserve($dir, '192.0.2.1'), false);
    same(file_exists($dir . '/state.json'), false);
});
test('Existing lock with missing state fails closed instead of resetting quotas', static function (): void {
    $dir = freshLedger(); same(reserve($dir, '192.0.2.1'), true);
    unlink($dir . '/state.json');
    same(reserve($dir, '192.0.2.1'), false);
    same(file_exists($dir . '/state.json'), false);
});
test('Existing state without lock is refused without creating a replacement lock', static function (): void {
    $dir = freshLedger(); same(reserve($dir, '192.0.2.1'), true);
    $snapshot = file_get_contents($dir . '/state.json');
    unlink($dir . '/lock');
    same(reserve($dir, '192.0.2.1'), false);
    same(file_exists($dir . '/lock'), false);
    same(file_get_contents($dir . '/state.json'), $snapshot);
});
test('Existing empty directory is refused rather than silently reinitialized', static function (): void {
    $dir = fresh();
    same(reserve($dir, '192.0.2.1'), false);
    same(array_values(array_diff(scandir($dir), ['.', '..'])), []);
});
$validBucket = substr(hash('sha256', 'mamourart-contact-v1|192.0.2.1'), 0, 32);
foreach (['', '{broken', '{}', 'null', '[null]', '[{"time":"1700000000","bucket":"bad"}]', str_repeat(' ', 4097),
    json_encode([['time' => -1, 'bucket' => $validBucket]]),
    json_encode([['time' => CLOCK + 1, 'bucket' => $validBucket]]),
    json_encode([['time' => CLOCK, 'bucket' => 'not-a-bucket']]),
    json_encode([['time' => CLOCK, 'bucket' => $validBucket, 'extra' => 1]]),
    json_encode(array_fill(0, 9, ['time' => CLOCK - 3600, 'bucket' => $validBucket])),
] as $index => $invalid) {
    test('Malformed or oversized stored state fails closed #' . $index, static function () use ($invalid): void {
        $dir = freshLedger(); same(reserve($dir, '192.0.2.1'), true);
        file_put_contents($dir . '/state.json', $invalid);
        same(reserve($dir, '192.0.2.1'), false);
        same(file_get_contents($dir . '/state.json'), $invalid);
    });
}

namespaceCopy(dirname(__DIR__, 2) . '/contact-rate-limit.php', $testRoot . '/fault-helper.php', 'MamourartContactFaults');
require __DIR__ . '/fault-functions.php';
require $testRoot . '/fault-helper.php';
foreach (['chmod', 'lock', 'read', 'temp', 'open-write', 'write', 'write-zero', 'write-partial', 'flush', 'close', 'rename'] as $fault) {
    test('Injected storage failure preserves previous snapshot: ' . $fault, static function () use ($fault): void {
        $dir = freshLedger(); same(reserve($dir, '192.0.2.1'), true);
        $snapshot = file_get_contents($dir . '/state.json');
        $GLOBALS['contact_fault'] = $fault;
        $GLOBALS['contact_partial_written'] = 0;
        $GLOBALS['contact_close_failed'] = false;
        try { same(\MamourartContactFaults\mamourart_contact_reserve($dir, '192.0.2.2', static fn(): int => CLOCK), false); }
        finally { $GLOBALS['contact_fault'] = ''; }
        same(file_get_contents($dir . '/state.json'), $snapshot);
        same(array_values(array_diff(scandir($dir), ['.', '..', 'lock', 'state.json'])), [], 'Temporary snapshot leaked');
        same(reserve($dir, '192.0.2.2'), true, 'Lock was not released after failure');
    });
}
foreach (['mkdir', 'open-write', 'open-lock', 'write', 'write-zero', 'write-partial', 'flush', 'close', 'close-lock', 'rename'] as $fault) {
    test('First initialization failure leaves final path absent and fresh retry succeeds: ' . $fault, static function () use ($fault): void {
        $dir = freshLedger();
        $GLOBALS['contact_fault'] = $fault;
        $GLOBALS['contact_partial_written'] = 0;
        $GLOBALS['contact_close_failed'] = false;
        $GLOBALS['contact_close_calls'] = 0;
        try { same(\MamourartContactFaults\mamourart_contact_reserve($dir, '192.0.2.1', static fn(): int => CLOCK), false); }
        finally { $GLOBALS['contact_fault'] = ''; }
        clearstatcache(true, $dir);
        same(file_exists($dir), false, 'Partial final ledger was published');
        same(array_values(array_diff(scandir(dirname($dir)), ['.', '..'])), [], 'Initialization staging files leaked after an ordinary failure');
        same(reserve($dir, '192.0.2.1'), true, 'Recoverable initialization failure blocked retry');
        same(count(state($dir)), 1);
        same(reserve($dir, '192.0.2.1'), true);
        same(reserve($dir, '192.0.2.1'), true);
        $snapshot = file_get_contents($dir . '/state.json');
        same(reserve($dir, '192.0.2.1'), false);
        same(file_get_contents($dir . '/state.json'), $snapshot);
    });
}
foreach (['lock', 'temp', 'snapshot-rename'] as $fault) {
    test('Failure after initial publication preserves empty ledger and permanent lock: ' . $fault, static function () use ($fault): void {
        $dir = freshLedger();
        $GLOBALS['contact_fault'] = $fault;
        try { same(\MamourartContactFaults\mamourart_contact_reserve($dir, '192.0.2.1', static fn(): int => CLOCK), false); }
        finally { $GLOBALS['contact_fault'] = ''; }
        same(file_get_contents($dir . '/state.json'), '[]', 'Published empty ledger was consumed or corrupted');
        check(is_file($dir . '/lock'), 'Published ledger has no stable lock');
        $lockInode = fileinode($dir . '/lock');
        same(array_values(array_diff(scandir($dir), ['.', '..', 'lock', 'state.json'])), [], 'Uncommitted snapshot leaked');
        same(reserve($dir, '192.0.2.1'), true);
        clearstatcache(true, $dir . '/lock');
        same(fileinode($dir . '/lock'), $lockInode, 'Retry replaced the published lock inode');
        same(count(state($dir)), 1);
    });
}

namespaceCopy(dirname(__DIR__, 2) . '/contact-rate-limit.php', $testRoot . '/interrupt-helper.php', 'MamourartContactInterrupt');
foreach (['before' => 73, 'after' => 74] as $phase => $expectedExit) {
    test('Interrupted initial directory publication recovers on fresh retry: ' . $phase, static function () use ($testRoot, $phase, $expectedExit): void {
        $dir = freshLedger();
        $configPath = fresh() . '/interrupt.json';
        file_put_contents($configPath, json_encode(['directory' => $dir, 'helper' => $testRoot . '/interrupt-helper.php', 'phase' => $phase], JSON_THROW_ON_ERROR));
        same(runChild(__DIR__ . '/interrupt-worker.php', [$configPath], null, $expectedExit), 'interrupted-' . $phase . "\n");
        clearstatcache(true, $dir);
        if ($phase === 'before') {
            same(file_exists($dir), false);
            same(count(glob(dirname($dir) . '/.mamourart-contact-init-*')), 1, 'Expected an unpublished orphan after interruption');
        } else {
            same(state($dir), []);
            check(is_file($dir . '/lock'), 'Published ledger lacked its permanent lock');
        }
        same(reserve($dir, '192.0.2.1'), true);
        same(count(state($dir)), 1);
    });
}

function startClockWorker(string $configPath): array {
    $process = proc_open([PHP_BINARY, '-n', '-d', 'disable_functions=mail', '-d', 'allow_url_fopen=0', __DIR__ . '/clock-worker.php', $configPath],
        [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
    check(is_resource($process), 'Cannot start clock ordering worker');
    stream_set_timeout($pipes[1], 15);
    return [$process, $pipes];
}
function finishClockWorker(?array &$worker, int $expectedClock): void {
    [$process, $pipes] = $worker;
    $clockLine = fgets($pipes[1]); $resultLine = fgets($pipes[1]);
    fclose($pipes[0]);
    $rest = stream_get_contents($pipes[1]); $errors = stream_get_contents($pipes[2]);
    fclose($pipes[1]); fclose($pipes[2]);
    $exit = proc_close($process); $worker = null;
    same($exit, 0, 'Clock worker failed: ' . $errors . $rest);
    same($errors, ''); same($rest, '');
    same($clockLine, 'clock:' . $expectedClock . "\n", 'Clock was evaluated before lock acquisition');
    same($resultLine, "result:1:1\n", 'Clock must be called exactly once inside the successful transaction');
}
namespaceCopy(dirname(__DIR__, 2) . '/contact-rate-limit.php', $testRoot . '/clock-helper.php', 'MamourartContactOrder');
test('Two processes acquire in reverse arrival order and read their clocks only inside the lock', static function () use ($testRoot): void {
    $dir = freshLedger(); same(reserve($dir, '198.51.100.254', CLOCK - 3600), true);
    $aClock = fresh() . '/clock'; $bClock = fresh() . '/clock';
    file_put_contents($aClock, (string)CLOCK); file_put_contents($bClock, (string)(CLOCK + 1));
    $aConfig = fresh() . '/clock.json'; $bConfig = fresh() . '/clock.json';
    foreach ([[$aConfig, $aClock, '192.0.2.1'], [$bConfig, $bClock, '192.0.2.2']] as [$path, $clock, $ip]) {
        file_put_contents($path, json_encode(['directory' => $dir, 'helper' => $testRoot . '/clock-helper.php', 'clock' => $clock, 'ip' => $ip], JSON_THROW_ON_ERROR));
    }
    $a = null; $b = null;
    try {
        $a = startClockWorker($aConfig);
        same(fgets($a[1][1]), "before-lock\n", 'First arrival evaluated its clock before the lock');
        $b = startClockWorker($bConfig);
        same(fgets($b[1][1]), "before-lock\n", 'Second arrival evaluated its clock before the lock');
        fwrite($b[1][0], "acquire\n"); fflush($b[1][0]);
        finishClockWorker($b, CLOCK + 1);
        file_put_contents($aClock, (string)(CLOCK + 2));
        fwrite($a[1][0], "acquire\n"); fflush($a[1][0]);
        finishClockWorker($a, CLOCK + 2);
        same(array_column(state($dir), 'time'), [CLOCK + 1, CLOCK + 2]);
    } finally {
        foreach ([$a, $b] as $worker) {
            if ($worker === null) continue;
            foreach ($worker[1] as $pipe) if (is_resource($pipe)) fclose($pipe);
            proc_terminate($worker[0]); proc_close($worker[0]);
        }
    }
});

$fixtures = [];
foreach (['public', 'private'] as $kind) {
    $fixture = fresh();
    namespaceCopy(dirname(__DIR__, 2) . '/contact-submit.php', $fixture . '/contact-submit.php', 'MamourartContactTests');
    copy(dirname(__DIR__, 2) . '/contact-rate-limit.php', $fixture . '/contact-rate-limit.php');
    if ($kind === 'private') file_put_contents($fixture . '/mamourart-form-test.html', 'local test form');
    $fixtures[$kind] = $fixture;
}
function endpoint(array $overrides = []): array {
    global $fixtures;
    $case = [
        'endpoint' => $fixtures['public'] . '/contact-submit.php', 'temp' => fresh(), 'now' => CLOCK,
        'server' => ['REQUEST_METHOD' => 'POST', 'CONTENT_TYPE' => 'application/x-www-form-urlencoded', 'HTTP_ORIGIN' => 'https://mamourart.com',
            'HTTP_SEC_FETCH_SITE' => 'same-origin', 'REMOTE_ADDR' => '192.0.2.1'],
        'post' => ['website' => '', 'name' => 'Alice Example', 'company' => 'Example', 'email' => 'alice@example.test',
            'service' => 'web', 'details' => 'A valid request with at least twenty characters.', 'privacy_ack' => 'yes'],
    ];
    foreach ($overrides as $key => $value) {
        $case[$key] = in_array($key, ['server', 'post'], true) ? array_replace($case[$key], $value) : $value;
    }
    $case['body'] = $overrides['body'] ?? http_build_query($case['post'], '', '&', PHP_QUERY_RFC1738);
    if (!array_key_exists('CONTENT_LENGTH', $overrides['server'] ?? [])) $case['server']['CONTENT_LENGTH'] = (string)strlen($case['body']);
    $wire = $case;
    $wire['body'] = base64_encode($case['body']);
    $wire['post'] = array_map(static fn(mixed $value): mixed => is_string($value) ? base64_encode($value) : $value, $case['post']);
    $result = json_decode(runChild(__DIR__ . '/endpoint-worker.php', [], json_encode($wire, JSON_THROW_ON_ERROR)), true, 512, JSON_THROW_ON_ERROR);
    $result['temp'] = $case['temp'];
    if ($result['fatal'] !== null) check(!in_array($result['fatal']['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR], true), 'Endpoint fatal error');
    return $result;
}
function redirect(array $result, string $status, bool $private = false): void {
    $expected = $private ? 'mamourart-form-test.html?contact_status=' . $status : '/?contact_status=' . $status . '#quoteResult';
    check(in_array(['Location: ' . $expected, true, 303], $result['headers'], true), 'Unexpected redirect: ' . json_encode($result['headers']));
}
test('Endpoint accepts valid data and calls only the in-memory mail stub', static function (): void {
    $result = endpoint(); redirect($result, 'sent'); same(count($result['mails']), 1);
    same($result['mails'][0]['to'], 'contact@mamourart.com');
    check(str_contains($result['mails'][0]['headers'], 'Reply-To: alice@example.test'), 'Missing validated reply address');
    same(count(glob($result['temp'] . '/*/state.json')), 1);
    check(in_array(['Cache-Control: no-store', true, 0], $result['headers'], true), 'Missing no-store');
});
test('Endpoint denies exhausted IP without calling mail', static function (): void {
    $temp = fresh();
    for ($i = 0; $i < 3; ++$i) { $result = endpoint(['temp' => $temp, 'post' => ['company' => 'Company ' . $i]]); redirect($result, 'sent'); }
    $path = glob($temp . '/*/state.json')[0]; $snapshot = file_get_contents($path);
    for ($i = 0; $i < 5; ++$i) { $result = endpoint(['temp' => $temp, 'post' => ['company' => 'New company']]); redirect($result, 'error'); same($result['mails'], []); }
    same(file_get_contents($path), $snapshot);
    $result = endpoint(['temp' => $temp, 'server' => ['REMOTE_ADDR' => '192.0.2.2']]);
    redirect($result, 'sent'); same(count($result['mails']), 1);
});
test('Honeypot returns apparent success before storage or mail', static function (): void {
    $result = endpoint(['post' => ['website' => 'https://bot.invalid/']]);
    redirect($result, 'sent'); same($result['mails'], []); same(glob($result['temp'] . '/*'), []);
});
test('Endpoint storage failure refuses mail', static function (): void {
    $temp = fresh() . '/blocked'; file_put_contents($temp, 'not a directory');
    $result = endpoint(['temp' => $temp]); redirect($result, 'error'); same($result['mails'], []);
});
test('Private-form redirect stays local', static function () use ($fixtures): void {
    $result = endpoint(['endpoint' => $fixtures['private'] . '/contact-submit.php']);
    redirect($result, 'sent', true);
});
test('Mail failure returns error and conservatively retains its reservation', static function (): void {
    $result = endpoint(['mail_ok' => false]); redirect($result, 'error'); same(count($result['mails']), 1);
    same(count(json_decode(file_get_contents(glob($result['temp'] . '/*/state.json')[0]), true)), 1);
});
$invalidCases = [
    'invalid email' => ['post' => ['email' => 'broken']],
    'email header injection' => ['post' => ['email' => "alice@example.test\r\nBcc: victim@example.test"]],
    'name line break' => ['post' => ['name' => "Alice\nBcc: injected"]],
    'company line break' => ['post' => ['company' => "Example\rInjected"]],
    'control character' => ['post' => ['details' => "A lengthy description containing \x01 a control"]],
    'malformed UTF-8' => ['post' => ['name' => "Alice\xff"]],
    'short details' => ['post' => ['details' => 'short']],
    'long details' => ['post' => ['details' => str_repeat('x', 3501)]],
    'long name' => ['post' => ['name' => str_repeat('x', 121)]],
    'missing consent' => ['post' => ['privacy_ack' => '']],
    'unknown service' => ['post' => ['service' => 'unknown']],
    'foreign origin' => ['server' => ['HTTP_ORIGIN' => 'https://attacker.invalid']],
    'foreign fetch site' => ['server' => ['HTTP_SEC_FETCH_SITE' => 'cross-site']],
    'malformed content length' => ['server' => ['CONTENT_LENGTH' => '-1']],
    'huge decoded field' => ['post' => ['details' => str_repeat('x', 14001)]],
    'oversized body' => ['server' => ['CONTENT_LENGTH' => '48001']],
];
foreach (['website', 'name', 'company', 'email', 'service', 'details', 'privacy_ack'] as $field) $invalidCases['array field ' . $field] = ['post' => [$field => ['injected']]];
foreach ($invalidCases as $name => $overrides) {
    test('Endpoint validation: ' . $name, static function () use ($overrides): void {
        $result = endpoint($overrides); redirect($result, 'error');
        same($result['mails'], []); same(glob($result['temp'] . '/*'), [], 'Invalid data touched rate-limit state');
    });
}
test('GET is rejected without storage or mail', static function (): void {
    // GET deliberately exits with a plain text body, so use the raw child output.
    global $fixtures;
    $temp = fresh();
    $case = ['endpoint' => $fixtures['public'] . '/contact-submit.php', 'temp' => $temp, 'now' => CLOCK,
        'post' => [], 'server' => ['REQUEST_METHOD' => 'GET']];
    $output = runChild(__DIR__ . '/endpoint-worker.php', [], json_encode($case, JSON_THROW_ON_ERROR));
    check(str_starts_with($output, 'Method not allowed'), 'GET body changed');
    $result = json_decode(substr($output, strlen('Method not allowed')), true, 512, JSON_THROW_ON_ERROR);
    same($result['status'], 405); same($result['mails'], []); same(glob($temp . '/*'), []);
    check(in_array(['Allow: POST', true, 0], $result['headers'], true), 'Missing Allow header');
});
test('Unsafe direct suite or worker invocation cannot reach application code', static function (): void {
    foreach (['suite.php', 'worker.php', 'endpoint-worker.php', 'clock-worker.php', 'interrupt-worker.php', 'mission39b.php', 'mission39d.php', 'slow-worker.php'] as $script) {
        $process = proc_open([PHP_BINARY, '-n', '-d', 'disable_functions=', __DIR__ . '/' . $script],
            [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes);
        check(is_resource($process), 'Cannot start guard test'); fclose($pipes[0]);
        same(stream_get_contents($pipes[1]), ''); $errors = stream_get_contents($pipes[2]);
        fclose($pipes[1]); fclose($pipes[2]); same(proc_close($process), 2);
        check(str_contains($errors, 'Unsafe test runtime'), 'Missing mandatory mail guard');
    }
});
require __DIR__ . '/mission39b.php';
require __DIR__ . '/mission39d.php';

echo "RESULT $passed passed, $failed failed; native mail disabled, isolated temporary state only.\n";
exit($failed === 0 ? 0 : 1);
