<?php
declare(strict_types=1);

// The launcher never loads application code. Run the entire suite in a fresh,
// configuration-free interpreter with native mail and URL streams disabled.
if (PHP_SAPI !== 'cli') {
    http_response_code(403);
    exit;
}
$command = [PHP_BINARY, '-n', '-d', 'disable_functions=mail', '-d',
    'allow_url_fopen=0', __DIR__ . '/suite.php'];
$process = proc_open($command, [0 => STDIN, 1 => STDOUT, 2 => STDERR], $pipes);
exit(is_resource($process) ? proc_close($process) : 2);
