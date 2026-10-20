<?php
/** Mission 24 contact endpoint for OVH PHP 8.2. Review and live-test before enabling. */
declare(strict_types=1);
header('Content-Type: text/html; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');
header('Cache-Control: no-store');

require_once __DIR__ . '/contact-rate-limit.php';

function reject(string $reason, string $status = 'error'): never {
    mamourart_contact_diagnostic($reason);
    back($status);
}

// HTML maxlength/minlength count UTF-16 code units, including two for emoji.
// PCRE is already required; mbstring/iconv are not needed.
function form_length(string $value): int {
    if (!preg_match('//u', $value)) return -1;
    return preg_match_all('/[\x{10000}-\x{10FFFF}]|[\s\S]/u', $value) +
        preg_match_all('/[\x{10000}-\x{10FFFF}]/u', $value);
}

function back(string $status): never {
    // When running in the password-protected test folder, return to its test form.
    // The destination is determined exclusively from a local file, never user input.
    $destination = is_file(__DIR__ . '/mamourart-form-test.html')
        ? 'mamourart-form-test.html?contact_status=' . $status
        : '/?contact_status=' . $status . '#quoteResult';
    header('Location: ' . $destination, true, 303);
    exit;
}
if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    header('Allow: POST');
    http_response_code(405);
    exit('Method not allowed');
}
$requestLength = (string)($_SERVER['CONTENT_LENGTH'] ?? '');
if (!preg_match('/\A[0-9]{1,8}\z/', $requestLength) || (int)$requestLength < 1 || (int)$requestLength > 48000) reject('validation');
// This HTML form is URL-encoded and has no uploads. Fail closed on a missing
// length, alternate parser, truncated PHP parsing or unexpected parameter shape.
$contentType = trim((string)($_SERVER['CONTENT_TYPE'] ?? ''));
if (!preg_match('~\Aapplication/x-www-form-urlencoded(?:\s*;\s*charset=(?:utf-8|"utf-8"))?\z~i', $contentType) ||
    !empty($_FILES)) reject('validation');
$fields = ['website', 'name', 'company', 'email', 'service', 'details', 'privacy_ack'];
if (array_diff(array_keys($_POST), $fields)) reject('validation');
$raw = file_get_contents('php://input', false, null, 0, 48001);
if (!is_string($raw) || strlen($raw) !== (int)$requestLength || strlen($raw) > 48000 ||
    preg_match('/%(?![a-f0-9]{2})/i', $raw)) reject('validation');
$pairs = explode('&', $raw);
if (count($pairs) > count($fields)) reject('validation');
$seen = [];
foreach ($pairs as $pair) {
    $parts = explode('=', $pair, 2);
    $field = urldecode($parts[0]);
    if (count($parts) !== 2 || !in_array($field, $fields, true) || isset($seen[$field])) reject('validation');
    $seen[$field] = true;
}
parse_str($raw, $parsed);
if ($parsed !== $_POST) reject('validation');
unset($raw, $parsed, $pairs, $seen);
$origin = strtolower((string)($_SERVER['HTTP_ORIGIN'] ?? ''));
if ($origin !== '' && !in_array($origin, ['https://mamourart.com', 'https://www.mamourart.com'], true)) reject('validation');
$fetchSite = strtolower((string)($_SERVER['HTTP_SEC_FETCH_SITE'] ?? ''));
if ($fetchSite !== '' && !in_array($fetchSite, ['same-origin', 'none'], true)) reject('validation');
// Form fields must be scalar strings. Reject array payloads before trim()/strlen().
foreach (['website', 'name', 'company', 'email', 'service', 'details', 'privacy_ack'] as $field) {
    if (isset($_POST[$field]) && (!is_string($_POST[$field]) || strlen($_POST[$field]) > 14000)) reject('validation');
}
// Honeypot. Hide the existence of the anti-spam rule from basic bots.
if (trim((string)($_POST['website'] ?? '')) !== '') reject('honeypot', 'sent');
$name = trim((string)($_POST['name'] ?? ''));
$company = trim((string)($_POST['company'] ?? ''));
$email = trim((string)($_POST['email'] ?? ''));
$service = (string)($_POST['service'] ?? '');
// Browser textarea lengths use LF; HTML form submission transports CRLF.
$details = str_replace(["\r\n", "\r"], "\n", trim((string)($_POST['details'] ?? '')));
$allowed = ['software'=>'Custom software', 'web'=>'Web/mobile', 'automation'=>'Automation and AI', 'transport'=>'Transport/logistics', 'other'=>'Other'];
if (form_length($name) < 2 || form_length($name) > 120 || form_length($company) < 0 || form_length($company) > 120 ||
    strlen($email) > 254 || !filter_var($email, FILTER_VALIDATE_EMAIL) ||
    preg_match('/[\r\n]/', $email) || !isset($allowed[$service]) ||
    form_length($details) < 20 || form_length($details) > 3500 ||
    ($_POST['privacy_ack'] ?? '') !== 'yes') reject('validation');
if (preg_match('/[\x00-\x08\x0B\x0C\x0E-\x1F]/', $name . $company . $details)) reject('validation');
// Names and company names must not contain line breaks (prevents forged mail body fields).
if (preg_match('/[\r\n]/', $name . $company)) reject('validation');
// Reject malformed UTF-8 (the form uses UTF-8).
if (!preg_match('//u', $name . $company . $details)) reject('validation');
// Short-lived state stores only timestamps and opaque hashes, never form contents.
$remote = (string)($_SERVER['REMOTE_ADDR'] ?? 'unknown');
$temporaryRoot = realpath(sys_get_temp_dir());
$publicRoot = realpath(__DIR__);
if ($temporaryRoot === false || !is_dir($temporaryRoot) || $publicRoot === false ||
    $temporaryRoot === $publicRoot || str_starts_with($temporaryRoot . '/', $publicRoot . '/')) reject('storage_failure');
$rateDirectory = $temporaryRoot . '/mamourart-contact-v2-' . substr(hash('sha256', __DIR__), 0, 16);
$clean = static fn(string $value): string => str_replace(["\r", "\0"], '', $value);
$body = "Nouvelle demande depuis mamourart.com\n\n" .
    "Nom : " . $clean($name) . "\nEntreprise : " . $clean($company) .
    "\nE-mail : " . $email . "\nService : " . $allowed[$service] .
    "\n\nDescription :\n" . $clean($details) . "\n";
$subject = '=?UTF-8?B?' . base64_encode('Mamourart — nouvelle demande de devis') . '?=';
$headers = [
    'From: Mamourart <contact@mamourart.com>',
    'Reply-To: ' . $email,
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'X-Content-Type-Options: nosniff',
];
// Exact validated values; JSON framing prevents ambiguous concatenation. No IP in
// the fingerprint: identical retries from another network are still duplicates.
$content = json_encode([$name, $company, $email, $service, $details], JSON_THROW_ON_ERROR);
$reason = null;
$ok = mamourart_contact_reserve($rateDirectory, $remote, static fn(): int => time(), $content,
    static fn(): bool => @mail('contact@mamourart.com', $subject, $body, implode("\r\n", $headers)), $reason);
if ($reason !== null) mamourart_contact_diagnostic($reason);
back($ok ? 'sent' : 'error');
