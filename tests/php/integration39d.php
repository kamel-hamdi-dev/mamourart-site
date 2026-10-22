<?php
declare(strict_types=1);
require_once __DIR__ . '/guard.php';

test('Integrated English POST keeps its static response language and generic error', static function () use ($fixtures): void {
    file_put_contents($fixtures['public'] . '/en.html', 'local English page');
    foreach ([['get' => ['lang' => 'en']], ['get' => ['lang' => 'en'], 'post' => ['email' => 'invalid']]] as $case) {
        $status = isset($case['post']) ? 'error' : 'sent'; $result = endpoint($case);
        check(in_array(['Location: /en.html?contact_status=' . $status . '#quoteResult', true, 303], $result['headers'], true), 'English response lost');
        same(count($result['mails']), $status === 'sent' ? 1 : 0);
    }
    $result = endpoint(['get' => ['lang' => 'https://attacker.invalid/']]); redirect($result, 'sent');
});

foreach (['fr', 'EN', 'en ', '', '//attacker.invalid/', "en\r\nLocation: https://attacker.invalid/", ['en'], ['url' => '//attacker.invalid/'], 1, true, null] as $index => $language) {
    test('Integrated redirect rejects non-exact English selector #' . $index, static function () use ($language): void {
        foreach (['sent', 'error'] as $status) {
            $case = ['get' => ['lang' => $language]];
            if ($status === 'error') $case['post'] = ['email' => 'invalid'];
            $result = endpoint($case);
            redirect($result, $status);
            same(count($result['mails']), $status === 'sent' ? 1 : 0);
        }
    });
}

test('Integrated English selector falls back to French when the local English document is absent', static function (): void {
    $public = fresh();
    namespaceCopy(dirname(__DIR__, 2) . '/contact-submit.php', $public . '/contact-submit.php', 'MamourartContactTests');
    copy(dirname(__DIR__, 2) . '/contact-rate-limit.php', $public . '/contact-rate-limit.php');
    foreach (['sent', 'error'] as $status) {
        $case = ['endpoint' => $public . '/contact-submit.php', 'get' => ['lang' => 'en']];
        if ($status === 'error') $case['post'] = ['email' => 'invalid'];
        redirect(endpoint($case), $status);
    }
});

test('Integrated language selector preserves the protected local test-form destination', static function () use ($fixtures): void {
    file_put_contents($fixtures['private'] . '/en.html', 'local English page');
    foreach (['sent', 'error'] as $status) {
        $case = ['endpoint' => $fixtures['private'] . '/contact-submit.php', 'get' => ['lang' => 'en']];
        if ($status === 'error') $case['post'] = ['email' => 'invalid'];
        redirect(endpoint($case), $status, true);
    }
});

test('Integrated FR/EN sent/error redirects use real loopback HTTP with only a local mail stub', static function (): void {
    $public = fresh(); $temporary = fresh(); $logs = fresh();
    namespaceCopy(dirname(__DIR__, 2) . '/contact-submit.php', $public . '/contact-submit.php', 'MamourartContactHttpTests');
    copy(dirname(__DIR__, 2) . '/contact-rate-limit.php', $public . '/contact-rate-limit.php');
    file_put_contents($public . '/en.html', 'local English page');
    $router = <<<'PHP'
<?php
declare(strict_types=1);
namespace MamourartContactHttpTests {
    function mail(string $to, string $subject, string $message, string $headers): bool {
        file_put_contents(MAIL_MARKER, "stub\n", FILE_APPEND);
        return true;
    }
    function sys_get_temp_dir(): string { return PRIVATE_TEMPORARY; }
}
namespace {
    // Generated only inside the suite's isolated temporary tree. No native mail.
    if (PHP_SAPI !== 'cli-server' || function_exists('mail')) {
        http_response_code(500); exit('Unsafe HTTP test runtime');
    }
    require __DIR__ . '/contact-submit.php';
}
PHP;
    $router = str_replace(['MAIL_MARKER', 'PRIVATE_TEMPORARY'], [var_export($logs . '/mail-stub', true), var_export($temporary, true)], $router);
    file_put_contents($public . '/router.php', $router);
    $listener = stream_socket_server('tcp://127.0.0.1:0', $errorNumber, $errorText);
    check(is_resource($listener), 'Cannot allocate loopback port: ' . $errorText);
    $address = stream_socket_get_name($listener, false); fclose($listener);
    $process = proc_open([PHP_BINARY, '-n', '-d', 'disable_functions=mail', '-d', 'allow_url_fopen=0', '-S', $address,
        '-t', $public, $public . '/router.php'], [0 => ['pipe', 'r'], 1 => ['file', $logs . '/server.log', 'a'],
        2 => ['file', $logs . '/server.log', 'a']], $pipes);
    check(is_resource($process), 'Cannot start isolated loopback PHP server');
    fclose($pipes[0]);
    try {
        $ready = false;
        for ($attempt = 0; $attempt < 100; ++$attempt) {
            $connection = @stream_socket_client('tcp://' . $address, $errorNumber, $errorText, 0.05);
            if (is_resource($connection)) { fclose($connection); $ready = true; break; }
            usleep(10000);
        }
        check($ready, 'Loopback PHP server did not become ready');
        foreach (['fr', 'en'] as $language) foreach (['sent', 'error'] as $status) {
            $body = http_build_query(['website' => '', 'name' => 'Alice Example', 'company' => 'Example ' . $language,
                'email' => $status === 'sent' ? 'alice@example.test' : 'invalid', 'service' => 'web',
                'details' => 'A valid fictitious loopback request with twenty characters.', 'privacy_ack' => 'yes']);
            $connection = stream_socket_client('tcp://' . $address, $errorNumber, $errorText, 2);
            check(is_resource($connection), 'Cannot connect to isolated loopback server');
            stream_set_timeout($connection, 3);
            $request = 'POST /contact-submit.php?lang=' . $language . " HTTP/1.1\r\nHost: " . $address .
                "\r\nContent-Type: application/x-www-form-urlencoded; charset=UTF-8\r\nContent-Length: " . strlen($body) .
                "\r\nConnection: close\r\n\r\n" . $body;
            same(fwrite($connection, $request), strlen($request), 'Incomplete loopback HTTP request');
            $response = stream_get_contents($connection); fclose($connection);
            check(str_starts_with($response, 'HTTP/1.1 303 '), 'Expected actual HTTP 303: ' . $response);
            $destination = $language === 'en' ? '/en.html' : '/';
            check(str_contains($response, "\r\nLocation: " . $destination . '?contact_status=' . $status . "#quoteResult\r\n"),
                'Wrong actual HTTP redirect: ' . $response);
            check(str_contains(strtolower($response), "\r\ncache-control: no-store\r\n"), 'HTTP result must remain private');
        }
        same(file_get_contents($logs . '/mail-stub'), "stub\nstub\n", 'Only the two valid local requests should call the stub');
    } finally {
        proc_terminate($process); proc_close($process);
    }
});
