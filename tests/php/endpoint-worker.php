<?php
declare(strict_types=1);
namespace {
    require __DIR__ . '/guard.php';
    $GLOBALS['contact_case'] = json_decode(stream_get_contents(STDIN), true, 512, JSON_THROW_ON_ERROR);
    require_isolated_test_path($GLOBALS['contact_case']['endpoint']);
    require_isolated_test_path($GLOBALS['contact_case']['temp']);
    if (isset($GLOBALS['contact_case']['diagnostics_dir'])) {
        require_isolated_test_path($GLOBALS['contact_case']['diagnostics_dir']);
        putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR=' . $GLOBALS['contact_case']['diagnostics_dir']);
    } else putenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR');
    $GLOBALS['contact_headers'] = [];
    $GLOBALS['contact_mails'] = [];
    $_SERVER = $GLOBALS['contact_case']['server'];
    // Base64 transports deliberately malformed UTF-8 through the JSON harness
    // unchanged, so the application (rather than JSON encoding) rejects it.
    $_POST = array_map(static fn(mixed $value): mixed => is_string($value) ? base64_decode($value, true) : $value,
        $GLOBALS['contact_case']['post']);
    register_shutdown_function(static function (): void {
        echo json_encode([
            'headers' => $GLOBALS['contact_headers'],
            'mails' => $GLOBALS['contact_mails'],
            'status' => http_response_code(),
            'fatal' => error_get_last(),
        ], JSON_THROW_ON_ERROR);
    });
}
namespace MamourartContactTests {
    function header(string $header, bool $replace = true, int $response_code = 0): void {
        $GLOBALS['contact_headers'][] = [$header, $replace, $response_code];
    }
    function mail(string $to, string $subject, string $message, string $headers): bool {
        $GLOBALS['contact_mails'][] = compact('to', 'subject', 'message', 'headers');
        return $GLOBALS['contact_case']['mail_ok'] ?? true;
    }
    function sys_get_temp_dir(): string { return $GLOBALS['contact_case']['temp']; }
    function time(): int { return $GLOBALS['contact_case']['now']; }
}
namespace {
    require $GLOBALS['contact_case']['endpoint'];
}
