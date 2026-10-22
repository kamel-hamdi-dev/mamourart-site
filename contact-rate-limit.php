<?php
declare(strict_types=1);

/** Publish a complete, empty ledger and its permanent lock before any admission. */
function mamourart_contact_initialize(string $directory): bool {
    $staging = null;
    $output = null;
    try {
        if (is_link($directory)) return false;
        if (is_dir($directory)) return true;
        if (file_exists($directory)) return false;
        $parent = realpath(dirname($directory));
        if ($parent === false) return false;
        $candidate = $parent . '/.mamourart-contact-init-' . bin2hex(random_bytes(12));
        if (!@mkdir($candidate, 0700)) return false;
        $staging = $candidate;
        $output = @fopen($staging . '/state.json', 'xb');
        if ($output === false) { $output = null; return false; }
        if (@fwrite($output, '[]') !== 2 || !@fflush($output)) return false;
        $closed = @fclose($output);
        $output = null;
        if (!$closed) return false;
        $output = @fopen($staging . '/lock', 'x');
        if ($output === false) { $output = null; return false; }
        $closed = @fclose($output);
        $output = null;
        if (!$closed) return false;

        clearstatcache(true, $directory);
        if (!file_exists($directory) && !is_link($directory) && @rename($staging, $directory)) {
            $staging = null;
            return true;
        }
        // A concurrent initializer may have published first. A ready directory
        // is nonempty, so POSIX rename cannot replace it or its lock inode.
        clearstatcache(true, $directory);
        return !is_link($directory) && is_dir($directory);
    } catch (Throwable $error) {
        return false;
    } finally {
        if (is_resource($output)) @fclose($output);
        if ($staging !== null) {
            @unlink($staging . '/state.json');
            @unlink($staging . '/lock');
            @rmdir($staging);
        }
    }
}

/**
 * Reserve both contact quotas in one transaction on a local/shared filesystem.
 * The directory and clock are supplied by the caller, never by form fields.
 */
function mamourart_contact_reserve(string $directory, string $remote, callable $clock,
    ?string $content = null, ?callable $send = null, ?string &$reason = null, bool $maintenance = false): bool {
    $reason = 'storage_failure';
    if (is_link($directory)) return false;
    if (!is_dir($directory) && !mamourart_contact_initialize($directory)) return false;
    if (is_link($directory) || !@chmod($directory, 0700)) return false;
    $directory = realpath($directory);
    if ($directory === false) return false;

    // This inode must stay in place: replacing/deleting it would split the lock.
    $lockPath = $directory . '/lock';
    if (is_link($lockPath)) return false;
    $lock = @fopen($lockPath, 'r+');
    if ($lock === false) return false;
    try {
        if (!@chmod($lockPath, 0600)) return false;
        if (!mamourart_contact_lock($lock, $reason)) return false;
        // Evaluate the clock only inside the transaction, after any lock wait.
        $now = $clock();
        if (!is_int($now) || $now < 0) return false;
        $statePath = $directory . '/state.json';
        clearstatcache(true, $statePath);
        if (is_link($statePath)) return false;
        // Once published, missing/corrupt state is never treated as a new ledger.
        if (!is_file($statePath) || !@chmod($statePath, 0600)) return false;
        $data = @file_get_contents($statePath, false, null, 0, 4097);
        if ($data === false || strlen($data) > 4096) return false;
        // Associative decoding alone would also turn the JSON object {} into [].
        if (!str_starts_with(ltrim($data), '[')) return false;
        $history = json_decode($data, true, 16, JSON_THROW_ON_ERROR);
        if (!is_array($history) || !array_is_list($history) || count($history) > 8) return false;

        $active = [];
        $bucket = substr(hash('sha256', 'mamourart-contact-v1|' . $remote), 0, 32);
        $ipCount = 0;
        foreach ($history as $entry) {
            // Corruption and a clock moving backwards fail closed, never reset quotas.
            if (!is_array($entry) || count(array_diff(array_keys($entry), ['time', 'bucket', 'digest', 'sent', 'key_id'])) !== 0 ||
                !isset($entry['time'], $entry['bucket']) || !is_int($entry['time']) ||
                $entry['time'] < 0 || $entry['time'] > $now || !is_string($entry['bucket']) ||
                !preg_match('/\A(?:[a-f0-9]{32}|[a-f0-9]{64})\z/', $entry['bucket'])) return false;
            if (array_key_exists('key_id', $entry) && (!is_string($entry['key_id']) ||
                !preg_match('/\A[a-f0-9]{64}\z/', $entry['key_id']))) return false;
            if (array_key_exists('digest', $entry) !== array_key_exists('sent', $entry)) return false;
            if (array_key_exists('digest', $entry) && (!isset($entry['sent']) ||
                !is_string($entry['digest']) || !preg_match('/\A[a-f0-9]{64}\z/', $entry['digest']) ||
                !is_bool($entry['sent']))) return false;
            if ($entry['time'] > $now - 3600) {
                $active[] = $entry;
                if ($entry['bucket'] === $bucket) ++$ipCount;
            }
        }
        $key = null;
        $identity = null;
        $dependent = false;
        foreach ($history as $entry) {
            if (strlen($entry['bucket']) === 64 || isset($entry['digest']) || isset($entry['key_id'])) {
                $dependent = true;
                // 39B HMAC records have no trustworthy key identity. Never silently
                // enroll them with a potentially already corrupted key.
                if (!isset($entry['key_id'])) { $reason = 'key_integrity'; return false; }
            }
        }
        if ($content !== null || $dependent) {
            $keyPath = $directory . '/key';
            if (is_link($keyPath)) return false;
            if (!is_file($keyPath)) {
                if ($dependent) { $reason = 'key_integrity'; return false; }
                if (!mamourart_contact_snapshot($directory, $keyPath, random_bytes(32))) return false;
            }
            if (!@chmod($keyPath, 0600)) return false;
            $key = @file_get_contents($keyPath, false, null, 0, 33);
            if (!is_string($key) || strlen($key) !== 32) { $reason = 'key_integrity'; return false; }
            $identity = hash('sha256', 'mamourart-contact-key-id-v1|' . $key);
            foreach ($history as $entry) {
                if (isset($entry['key_id']) && !hash_equals($entry['key_id'], $identity)) {
                    $reason = 'key_integrity'; return false;
                }
            }
        }
        if ($maintenance) {
            $partial = false;
            $scanned = 0;
            foreach (new \DirectoryIterator($directory) as $file) {
                if (++$scanned > 64) { $partial = true; break; }
                // Only this application's tempnam pattern, never arbitrary .state-*.
                if (!$file->isLink() && $file->isFile() &&
                    preg_match('/\A\.state-[A-Za-z0-9]{6}\z/', $file->getFilename()) &&
                    $file->getMTime() <= $now - 3600 && !@unlink($file->getPathname())) $partial = true;
            }
            foreach ($active as &$entry) {
                if ($entry['time'] <= $now - 300) unset($entry['digest'], $entry['sent']);
            }
            unset($entry);
            if ($active !== $history && !mamourart_contact_snapshot($directory, $statePath,
                json_encode($active, JSON_THROW_ON_ERROR))) return false;
            $reason = $partial ? 'maintenance_partial' : 'maintenance';
            return true;
        }
        $digest = null;
        if ($key !== null) {
            $legacyBucket = $bucket;
            $bucket = hash_hmac('sha256', 'mamourart-contact-ip-v1|' . $remote, $key);
            $ipCount = 0;
            foreach ($active as $entry) {
                if ($entry['bucket'] === $bucket || $entry['bucket'] === $legacyBucket) ++$ipCount;
            }
        }
        if ($content !== null) {
            if ($send === null || $key === null) return false;
            $digest = hash_hmac('sha256', 'mamourart-contact-dedup-v1|' . $content, $key);
            foreach ($active as $entry) {
                if (isset($entry['digest']) && $entry['time'] > $now - 300 &&
                    hash_equals($entry['digest'], $digest)) {
                    $reason = $entry['sent'] ? 'already_processed' : 'pending';
                    return $entry['sent'];
                }
            }
        }
        // A quota refusal never rewrites the ledger or consumes capacity.
        if ($ipCount >= 3) { $reason = 'individual_quota'; return false; }
        if (count($active) >= 8) { $reason = 'global_quota'; return false; }
        // Strip expired fingerprints while retaining the one-hour quota reservations.
        foreach ($active as &$entry) {
            if ($entry['time'] <= $now - 300) unset($entry['digest'], $entry['sent']);
        }
        unset($entry);
        if ($identity !== null) {
            foreach ($active as &$entry) $entry['key_id'] = $identity;
            unset($entry);
        }
        $active[] = ['time' => $now, 'bucket' => $bucket];
        $last = count($active) - 1;
        if ($identity !== null) $active[$last]['key_id'] = $identity;
        if ($digest !== null) {
            $active[$last]['digest'] = $digest;
            $active[$last]['sent'] = false;
        }
        // Persist a pending reservation BEFORE invoking mail. Keep the permanent
        // exclusive lock through mail and completion so concurrent duplicates cannot send.
        if (!mamourart_contact_snapshot($directory, $statePath, json_encode($active, JSON_THROW_ON_ERROR))) return false;
        if ($digest === null) { $reason = 'reserved'; return true; }
        try { $sent = $send() === true; }
        catch (Throwable $error) { $sent = false; }
        if ($sent) $active[$last]['sent'] = true;
        else unset($active[$last]['digest'], $active[$last]['sent']);
        // Keep failed-mail quota reservations, as before; remove only their fingerprint.
        // A failed completion write remains pending and must never claim success.
        if (!mamourart_contact_snapshot($directory, $statePath, json_encode($active, JSON_THROW_ON_ERROR))) return false;
        $reason = $sent ? 'sent' : 'mail_failure';
        return $sent;
    } catch (Throwable $error) {
        return false;
    } finally {
        @flock($lock, LOCK_UN);
        @fclose($lock);
    }
}

/** No blocking flock: 250 ms voluntary wait budget, at most 26 attempts. */
function mamourart_contact_lock($lock, ?string &$reason): bool {
    $deadline = hrtime(true) + 250000000;
    for ($attempt = 0; $attempt < 26; ++$attempt) {
        $wouldBlock = 0;
        if (@flock($lock, LOCK_EX | LOCK_NB, $wouldBlock)) return true;
        if ($wouldBlock !== 1) return false;
        if ($attempt === 25 || hrtime(true) >= $deadline) break;
        usleep((int)min(10000, max(0, intdiv($deadline - hrtime(true), 1000))));
        if (hrtime(true) >= $deadline) break;
    }
    $reason = 'lock_busy';
    return false;
}

/** Atomic publication; callers hold the permanent ledger lock. */
function mamourart_contact_snapshot(string $directory, string $path, string $snapshot): bool {
    $temporary = null;
    $output = null;
    try {
        $temporary = @tempnam($directory, '.state-');
        if ($temporary === false) { $temporary = null; return false; }
        if (dirname($temporary) !== $directory) return false;
        $output = @fopen($temporary, 'wb');
        if ($output === false) { $output = null; return false; }
        if (@fwrite($output, $snapshot) !== strlen($snapshot) || !@fflush($output)) return false;
        $closed = @fclose($output);
        $output = null;
        if (!$closed || !@rename($temporary, $path)) return false;
        $temporary = null;
        return true;
    } finally {
        if (is_resource($output)) @fclose($output);
        if ($temporary !== null) @unlink($temporary);
    }
}

/** Optional observations. Explicit outcome lets private maintenance report failures. */
function mamourart_contact_diagnostic(string $reason): string {
    $allowed = ['validation', 'honeypot', 'individual_quota', 'global_quota',
        'already_processed', 'pending', 'storage_failure', 'mail_failure', 'lock_busy', 'key_integrity'];
    $maintenance = $reason === 'maintenance';
    if (!$maintenance && !in_array($reason, $allowed, true)) return 'disabled';
    $directory = getenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR');
    if ($directory === false || $directory === '') return 'disabled';
    if ($directory[0] !== '/' || is_link($directory) || !is_dir($directory)) return 'error';
    $directory = realpath($directory);
    $root = realpath($_SERVER['DOCUMENT_ROOT'] ?? __DIR__);
    if ($directory === false || $root === false || $directory === $root ||
        str_starts_with($directory . '/', $root . '/') ||
        (@fileperms($directory) & 0777) !== 0700) return 'error';
    $path = $directory . '/observations.json';
    if (is_link($path)) return 'error';
    if ($maintenance && !file_exists($path)) return 'ok';
    $existed = is_file($path);
    $file = @fopen($path, 'c+');
    if ($file === false) return 'error';
    try {
        if (!@chmod($path, 0600)) return 'error';
        $wouldBlock = 0;
        if (!@flock($file, LOCK_EX | LOCK_NB, $wouldBlock)) return $wouldBlock === 1 ? 'partial' : 'error';
        $now = time(); $day = intdiv($now, 86400);
        $raw = @stream_get_contents($file, 2049);
        if ($raw === false) return 'error';
        $state = json_decode($raw, true);
        $valid = is_array($state) && isset($state['day']) && is_int($state['day']) &&
            $state['day'] >= 0 && $state['day'] <= $day &&
            count(array_diff(array_keys($state), ['day', ...$allowed])) === 0;
        if ($valid) foreach ($state as $key => $value) {
            if ($key === 'day') continue;
            if (!is_array($value) || count($value) !== 2 || !isset($value['minute'], $value['minutes']) ||
                !is_int($value['minute']) || !is_int($value['minutes']) || $value['minutes'] < 1 ||
                $value['minutes'] > 1440 || intdiv($value['minute'], 1440) !== $state['day']) $valid = false;
        }
        $repair = ($existed || $raw !== '') && (strlen($raw) > 2048 || !$valid);
        if ($repair && !$maintenance) return 'error';
        if (!$valid || $repair || $state['day'] !== $day) $state = ['day' => $day];
        elseif ($maintenance) return 'ok';
        if (!$maintenance) {
            $minute = intdiv($now, 60);
            if (($state[$reason]['minute'] ?? null) === $minute) return 'ok';
            $state[$reason] = ['minute' => $minute, 'minutes' => min(1440, ($state[$reason]['minutes'] ?? 0) + 1)];
        }
        $data = json_encode($state, JSON_THROW_ON_ERROR);
        if (!@rewind($file) || @fwrite($file, $data) !== strlen($data) ||
            !@ftruncate($file, strlen($data)) || !@fflush($file)) return 'error';
        return $repair ? 'partial' : 'ok';
    } catch (Throwable $error) {
        return 'error';
    } finally {
        @flock($file, LOCK_UN);
        @fclose($file);
    }
}
