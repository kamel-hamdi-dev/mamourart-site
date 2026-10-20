<?php
declare(strict_types=1);
require __DIR__ . '/guard.php';
require dirname(__DIR__, 2) . '/contact-rate-limit.php';

// Pipes supply a barrier: the parent releases every worker only after every
// worker is ready. No HTTP, DNS or other network connection is involved.
require_isolated_test_path($argv[1]);
$config = json_decode((string)file_get_contents($argv[1]), true, 512, JSON_THROW_ON_ERROR);
require_isolated_test_path($config['directory']);
fwrite(STDOUT, "ready\n");
fflush(STDOUT);
if (fgets(STDIN) !== "go\n") exit(2);
if (isset($config['content'])) {
    $reason = null;
    $ok = mamourart_contact_reserve($config['directory'], $config['ip'], static fn(): int => $config['now'],
        $config['content'], static function () use ($config): bool {
            file_put_contents($config['directory'] . '/mail-calls', "stub\n", FILE_APPEND);
            return true;
        }, $reason);
    echo json_encode([$ok, $reason]) . "\n";
} else echo mamourart_contact_reserve($config['directory'], $config['ip'], static fn(): int => $config['now']) ? "1\n" : "0\n";
