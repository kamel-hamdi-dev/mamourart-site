<?php
declare(strict_types=1);
namespace {
    require __DIR__ . '/guard.php';
    require_isolated_test_path($argv[1]);
    $GLOBALS['interrupt_case'] = json_decode(file_get_contents($argv[1]), true, 512, JSON_THROW_ON_ERROR);
    foreach (['directory', 'helper'] as $key) require_isolated_test_path($GLOBALS['interrupt_case'][$key]);
}
namespace MamourartContactInterrupt {
    function rename(string $from, string $to): bool {
        $case = $GLOBALS['interrupt_case'];
        if ($to !== $case['directory'] || !\is_dir($from)) return \rename($from, $to);
        if (!\is_file($from . '/lock') || \file_get_contents($from . '/state.json') !== '[]') {
            \fwrite(STDERR, "Attempted publication of incomplete initial ledger.\n");
            exit(2);
        }
        if ($case['phase'] === 'before') {
            echo "interrupted-before\n";
            exit(73); // Simulates interruption: exit bypasses the helper's finally.
        }
        $result = \rename($from, $to);
        if ($result && $case['phase'] === 'after') {
            echo "interrupted-after\n";
            exit(74);
        }
        return $result;
    }
}
namespace {
    require $GLOBALS['interrupt_case']['helper'];
    \MamourartContactInterrupt\mamourart_contact_reserve($GLOBALS['interrupt_case']['directory'], '192.0.2.1', static fn(): int => 1700000000);
    fwrite(STDERR, "Requested publication interruption was not reached.\n");
    exit(2);
}
