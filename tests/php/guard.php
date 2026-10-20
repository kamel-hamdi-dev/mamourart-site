<?php
declare(strict_types=1);

// Every executable test checks this BEFORE loading any application code.
if (PHP_SAPI !== 'cli' || function_exists('mail') ||
    !in_array('mail', array_map('trim', explode(',', (string)ini_get('disable_functions'))), true)) {
    fwrite(STDERR, "Unsafe test runtime: use php tests/php/run.php (native mail must be disabled).\n");
    exit(2);
}

function require_isolated_test_path(string $path): void {
    $prefix = preg_quote(rtrim(sys_get_temp_dir(), '/'), '~');
    if (!preg_match('~\A' . $prefix . '/mamourart-m28-tests-[a-f0-9]{24}/~', $path) ||
        preg_match('~(?:\A|/)\.{1,2}(?:/|\z)~', $path)) {
        fwrite(STDERR, "Refusing a path outside the isolated Mission 28 test tree.\n");
        exit(2);
    }
}
