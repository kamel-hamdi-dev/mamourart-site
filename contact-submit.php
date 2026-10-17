<?php
/** Mission 24 contact endpoint for OVH PHP 8.2. Review and live-test before enabling. */
declare(strict_types=1);
header('Content-Type: text/html; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');
header('Cache-Control: no-store');

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
if ((int)($_SERVER['CONTENT_LENGTH'] ?? 0) > 12000) back('error');
$origin = strtolower((string)($_SERVER['HTTP_ORIGIN'] ?? ''));
if ($origin !== '' && !in_array($origin, ['https://mamourart.com', 'https://www.mamourart.com'], true)) back('error');
$fetchSite = strtolower((string)($_SERVER['HTTP_SEC_FETCH_SITE'] ?? ''));
if ($fetchSite !== '' && !in_array($fetchSite, ['same-origin', 'none'], true)) back('error');
// Form fields must be scalar strings. Reject array payloads before trim()/strlen().
foreach (['website', 'name', 'company', 'email', 'service', 'details', 'privacy_ack'] as $field) {
    if (isset($_POST[$field]) && !is_string($_POST[$field])) back('error');
}
// Honeypot. Hide the existence of the anti-spam rule from basic bots.
if (trim((string)($_POST['website'] ?? '')) !== '') back('sent');
$name = trim((string)($_POST['name'] ?? ''));
$company = trim((string)($_POST['company'] ?? ''));
$email = trim((string)($_POST['email'] ?? ''));
$service = (string)($_POST['service'] ?? '');
$details = trim((string)($_POST['details'] ?? ''));
$allowed = ['software'=>'Custom software', 'web'=>'Web/mobile', 'automation'=>'Automation and AI', 'transport'=>'Transport/logistics', 'other'=>'Other'];
if (strlen($name) < 2 || strlen($name) > 120 || strlen($company) > 120 ||
    strlen($email) > 254 || !filter_var($email, FILTER_VALIDATE_EMAIL) ||
    preg_match('/[\r\n]/', $email) || !isset($allowed[$service]) ||
    strlen($details) < 20 || strlen($details) > 3500 ||
    ($_POST['privacy_ack'] ?? '') !== 'yes') back('error');
if (preg_match('/[\x00-\x08\x0B\x0C\x0E-\x1F]/', $name . $company . $details)) back('error');
// Names and company names must not contain line breaks (prevents forged mail body fields).
if (preg_match('/[\r\n]/', $name . $company)) back('error');
// Reject malformed UTF-8 (the form uses UTF-8).
if (!preg_match('//u', $name . $company . $details)) back('error');
// Short-lived rate-limiting state stores only opaque hashes, never form contents.
$remote = (string)($_SERVER['REMOTE_ADDR'] ?? 'unknown');
$bucket = substr(hash('sha256', 'mamourart-contact-v1|' . $remote), 0, 32);
foreach (["mamourart_form_all"=>8, "mamourart_form_{$bucket}"=>3] as $key=>$max) {
    $path = sys_get_temp_dir() . '/' . $key . '.txt';
    $file = @fopen($path, 'c+');
    if ($file === false || !flock($file, LOCK_EX)) back('error');
    $data = stream_get_contents($file);
    $history = json_decode($data ?: '[]', true);
    if (!is_array($history)) $history = [];
    $history = array_values(array_filter($history, fn($t) => is_numeric($t) && (time() - (int)$t) < 3600));
    if (count($history) >= $max) {
        flock($file, LOCK_UN); fclose($file); back('error');
    }
    $history[] = time();
    rewind($file); ftruncate($file, 0); fwrite($file, json_encode($history)); fflush($file);
    flock($file, LOCK_UN); fclose($file);
}
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
$ok = @mail('contact@mamourart.com', $subject, $body, implode("\r\n", $headers));
back($ok ? 'sent' : 'error');
