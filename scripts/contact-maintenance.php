<?php
/** Private cleanup: 0 complete, 1 error, 2 usage, 3 partial (retry/inspect). */
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
$publicRoot = realpath($argv[1] ?? dirname(__DIR__));
if ($publicRoot === false || !is_file($publicRoot . '/contact-submit.php') ||
    !is_file($publicRoot . '/contact-rate-limit.php')) exit(2);
$_SERVER['DOCUMENT_ROOT'] = $publicRoot;
require $publicRoot . '/contact-rate-limit.php';
$temp = realpath(sys_get_temp_dir());
if ($temp === false || $temp === $publicRoot || str_starts_with($temp . '/', $publicRoot . '/')) exit(1);
$directory = $temp . '/mamourart-contact-v2-' . substr(hash('sha256', $publicRoot), 0, 16);
$reason = null;
$ok = (!is_link($directory) && !file_exists($directory)) ||
    mamourart_contact_reserve($directory, '', static fn(): int => time(), null, null, $reason, true);
$diagnostics = mamourart_contact_diagnostic('maintenance');
if (!$ok || $diagnostics === 'error') exit(1);
exit($reason === 'maintenance_partial' || $diagnostics === 'partial' ? 3 : 0);
