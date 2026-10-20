<?php
declare(strict_types=1);
require __DIR__ . '/guard.php';
require_isolated_test_path($argv[1]);
$config = json_decode(file_get_contents($argv[1]), true, 16, JSON_THROW_ON_ERROR);
require_isolated_test_path($config['directory']);
require dirname(__DIR__, 2) . '/contact-rate-limit.php';
$reason = null;
$result = mamourart_contact_reserve($config['directory'], '192.0.2.1', static fn(): int => $config['now'],
    'slow fixture', static function () use ($config): bool {
        echo "transport\n"; fflush(STDOUT);
        if ($config['mode'] === 'crash_before') exit(77);
        if ($config['mode'] === 'crash_after') {
            file_put_contents($config['directory'] . '/accepted', 'stub'); exit(78);
        }
        if (fgets(STDIN) !== "finish\n") exit(2);
        return true;
    }, $reason);
echo json_encode([$result, $reason]) . "\n";
