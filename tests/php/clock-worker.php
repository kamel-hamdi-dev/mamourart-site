<?php
declare(strict_types=1);
namespace {
    require __DIR__ . '/guard.php';
    require_isolated_test_path($argv[1]);
    $GLOBALS['clock_case'] = json_decode(file_get_contents($argv[1]), true, 512, JSON_THROW_ON_ERROR);
    foreach (['directory', 'helper', 'clock'] as $key) require_isolated_test_path($GLOBALS['clock_case'][$key]);
}
namespace MamourartContactOrder {
    function flock($stream, int $operation, &$would_block = null): bool {
        if ($operation === LOCK_EX) {
            \fwrite(STDOUT, "before-lock\n");
            \fflush(STDOUT);
            if (\fgets(STDIN) !== "acquire\n") exit(2);
        }
        return \flock($stream, $operation, $would_block);
    }
}
namespace {
    require $GLOBALS['clock_case']['helper'];
    $calls = 0;
    $clock = static function () use (&$calls): int {
        ++$calls;
        $case = $GLOBALS['clock_case'];
        // A separate open-file description must be unable to take the lock while
        // the helper executes this callback, even in the same process.
        $probe = fopen($case['directory'] . '/lock', 'r+');
        if ($probe === false || flock($probe, LOCK_EX | LOCK_NB)) {
            fwrite(STDERR, "Clock callback ran without the exclusive ledger lock.\n");
            exit(2);
        }
        fclose($probe);
        $now = (int)file_get_contents($case['clock']);
        fwrite(STDOUT, 'clock:' . $now . "\n");
        fflush(STDOUT);
        return $now;
    };
    $allowed = \MamourartContactOrder\mamourart_contact_reserve($GLOBALS['clock_case']['directory'], $GLOBALS['clock_case']['ip'], $clock);
    echo 'result:' . (int)$allowed . ':' . $calls . "\n";
}
