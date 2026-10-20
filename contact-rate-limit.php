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
        if (!@chmod($lockPath, 0600) || !@flock($lock, LOCK_EX)) return false;
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
            if (!is_array($entry) || !in_array(count($entry), [2, 4], true) ||
                !isset($entry['time'], $entry['bucket']) || !is_int($entry['time']) ||
                $entry['time'] < 0 || $entry['time'] > $now || !is_string($entry['bucket']) ||
                !preg_match('/\A(?:[a-f0-9]{32}|[a-f0-9]{64})\z/', $entry['bucket'])) return false;
            if (count($entry) === 4 && (!isset($entry['digest'], $entry['sent']) ||
                !is_string($entry['digest']) || !preg_match('/\A[a-f0-9]{64}\z/', $entry['digest']) ||
                !is_bool($entry['sent']))) return false;
            if ($entry['time'] > $now - 3600) {
                $active[] = $entry;
                if ($entry['bucket'] === $bucket) ++$ipCount;
            }
        }
        if ($maintenance) {
            // Inspect at most 64 directory entries per run. Never touch the lock/key,
            // symlinks or recent snapshots; only crash leftovers older than one hour.
            $scanned = 0;
            foreach (new \DirectoryIterator($directory) as $file) {
                if (++$scanned > 64) break;
                if (!$file->isLink() && $file->isFile() &&
                    str_starts_with($file->getFilename(), '.state-') && $file->getMTime() <= $now - 3600)
                    @unlink($file->getPathname());
            }
            foreach ($active as &$entry) {
                if ($entry['time'] <= $now - 300) unset($entry['digest'], $entry['sent']);
            }
            unset($entry);
            $reason = 'maintenance';
            return $active === $history || mamourart_contact_snapshot($directory, $statePath,
                json_encode($active, JSON_THROW_ON_ERROR));
        }
        $digest = null;
        if ($content !== null) {
            if ($send === null) return false;
            // Generated locally, never supplied by HTTP and never committed to Git.
            $keyPath = $directory . '/key';
            if (is_link($keyPath)) return false;
            if (!is_file($keyPath)) {
                // A lost key must never silently disable an existing deduplication ledger.
                foreach ($history as $entry) if (isset($entry['digest']) || strlen($entry['bucket']) === 64) return false;
                if (!mamourart_contact_snapshot($directory, $keyPath, random_bytes(32))) return false;
            }
            if (!@chmod($keyPath, 0600)) return false;
            $key = @file_get_contents($keyPath, false, null, 0, 33);
            if (!is_string($key) || strlen($key) !== 32) return false;
            $legacyBucket = $bucket;
            $bucket = hash_hmac('sha256', 'mamourart-contact-ip-v1|' . $remote, $key);
            $ipCount = 0;
            foreach ($active as $entry) {
                if ($entry['bucket'] === $bucket || $entry['bucket'] === $legacyBucket) ++$ipCount;
            }
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
        $active[] = ['time' => $now, 'bucket' => $bucket];
        $last = count($active) - 1;
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

/** Optional aggregate observations, never request data. Disabled without a private directory. */
function mamourart_contact_diagnostic(string $reason): void {
    $allowed = ['validation', 'honeypot', 'individual_quota', 'global_quota',
        'already_processed', 'pending', 'storage_failure', 'mail_failure'];
    $maintenance = $reason === 'maintenance';
    if (!$maintenance && !in_array($reason, $allowed, true)) return;
    $directory = getenv('MAMOURART_CONTACT_DIAGNOSTICS_DIR');
    if (!is_string($directory) || $directory === '' || $directory[0] !== '/' ||
        is_link($directory) || !is_dir($directory)) return;
    $directory = realpath($directory);
    // Administrator must provision a private directory outside the public document root.
    $root = realpath($_SERVER['DOCUMENT_ROOT'] ?? __DIR__);
    if ($directory === false || $root === false || $directory === $root ||
        str_starts_with($directory . '/', $root . '/') ||
        (fileperms($directory) & 0777) !== 0700) return;
    $path = $directory . '/observations.json';
    if (is_link($path)) return;
    if ($maintenance && !is_file($path)) return;
    $file = @fopen($path, 'c+');
    if ($file === false) return;
    try {
        if (!@chmod($path, 0600) || !@flock($file, LOCK_EX | LOCK_NB)) return;
        $now = time();
        $day = intdiv($now, 86400);
        $raw = stream_get_contents($file, 2049);
        if ($raw === false || strlen($raw) > 2048) return;
        $state = json_decode($raw, true);
        if (!is_array($state) || ($state['day'] ?? null) !== $day) $state = ['day' => $day];
        elseif ($maintenance) return;
        $state = array_intersect_key($state, array_flip(['day', ...$allowed]));
        // One observation per reason/minute, at most 8 writes/minute; no unlimited log.
        $minute = intdiv($now, 60);
        if (!$maintenance) {
            if (($state[$reason]['minute'] ?? null) === $minute) return;
            $state[$reason] = ['minute' => $minute, 'minutes' => min(1440, (int)($state[$reason]['minutes'] ?? 0) + 1)];
        }
        $data = json_encode($state);
        if ($data === false) return;
        rewind($file);
        if (@fwrite($file, $data) === strlen($data)) { @ftruncate($file, strlen($data)); @fflush($file); }
    } catch (Throwable $error) {
        // Diagnostics must never alter admission or disclose paths through PHP warnings.
    } finally {
        @flock($file, LOCK_UN);
        @fclose($file);
    }
}
