<?php
/** Private scheduled cleanup; never include this file in deploy-manifest.json. */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
// Optional CLI-only public-root argument lets the scheduler keep this script private.
$publicRoot = realpath($argv[1] ?? dirname(__DIR__));
if ($publicRoot === false || !is_file($publicRoot . '/contact-submit.php') ||
    !is_file($publicRoot . '/contact-rate-limit.php')) exit(2);
$_SERVER['DOCUMENT_ROOT'] = $publicRoot;
require $publicRoot . '/contact-rate-limit.php';
$directory = sys_get_temp_dir() . '/mamourart-contact-v2-' . substr(hash('sha256', $publicRoot), 0, 16);
$reason = null;
// Do not initialize unused storage; never delete or replace the permanent lock/key.
$ok = !file_exists($directory) || mamourart_contact_reserve($directory, '', static fn(): int => time(), null, null, $reason, true);
mamourart_contact_diagnostic('maintenance');
exit($ok ? 0 : 1);
