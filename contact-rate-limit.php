<?php
declare(strict_types=1);

/**
 * Reserve both contact quotas in one transaction on a local/shared filesystem.
 * The directory and clock are supplied by the caller, never by form fields.
 */
function mamourart_contact_reserve(string $directory, string $remote, int $now): bool {
    if ($now < 0 || is_link($directory)) return false;
    if (!is_dir($directory) && !@mkdir($directory, 0700) && !is_dir($directory)) return false;
    if (is_link($directory) || !@chmod($directory, 0700)) return false;
    $directory = realpath($directory);
    if ($directory === false) return false;

    // This inode must stay in place: replacing/deleting it would split the lock.
    $lockPath = $directory . '/lock';
    if (is_link($lockPath)) return false;
    $lock = @fopen($lockPath, 'x');
    $createdLock = $lock !== false;
    if (!$createdLock) $lock = @fopen($lockPath, 'r+');
    if ($lock === false) return false;
    $temporary = null;
    $output = null;
    try {
        if (!@flock($lock, LOCK_EX)) return false;
        $statePath = $directory . '/state.json';
        clearstatcache(true, $statePath);
        if (is_link($statePath)) return false;
        $history = [];
        if (file_exists($statePath)) {
            if (!is_file($statePath)) return false;
            $data = @file_get_contents($statePath, false, null, 0, 4097);
            if ($data === false || strlen($data) > 4096) return false;
            // Associative decoding alone would also turn the JSON object {} into [].
            if (!str_starts_with(ltrim($data), '[')) return false;
            $history = json_decode($data, true, 16, JSON_THROW_ON_ERROR);
            if (!is_array($history) || !array_is_list($history) || count($history) > 8) return false;
        } elseif (!$createdLock) return false;

        $active = [];
        $bucket = substr(hash('sha256', 'mamourart-contact-v1|' . $remote), 0, 32);
        $ipCount = 0;
        foreach ($history as $entry) {
            // Corruption and a clock moving backwards fail closed, never reset quotas.
            if (!is_array($entry) || count($entry) !== 2 ||
                !isset($entry['time'], $entry['bucket']) || !is_int($entry['time']) ||
                $entry['time'] < 0 || $entry['time'] > $now || !is_string($entry['bucket']) ||
                !preg_match('/\A[a-f0-9]{32}\z/', $entry['bucket'])) return false;
            if ($entry['time'] > $now - 3600) {
                $active[] = $entry;
                if ($entry['bucket'] === $bucket) ++$ipCount;
            }
        }
        // Neither a refusal nor expiry cleanup alone writes or consumes any quota.
        if (count($active) >= 8 || $ipCount >= 3) return false;
        $active[] = ['time' => $now, 'bucket' => $bucket];
        $snapshot = json_encode($active, JSON_THROW_ON_ERROR);

        // Commit the entire ledger at once; an incomplete write leaves the old state.
        $temporary = @tempnam($directory, '.state-');
        if ($temporary === false) { $temporary = null; return false; }
        if (dirname($temporary) !== $directory) return false;
        $output = @fopen($temporary, 'wb');
        if ($output === false) { $output = null; return false; }
        if (@fwrite($output, $snapshot) !== strlen($snapshot) || !@fflush($output)) return false;
        $closed = @fclose($output);
        $output = null;
        if (!$closed || !@rename($temporary, $statePath)) return false;
        $temporary = null;
        return true;
    } catch (Throwable $error) {
        return false;
    } finally {
        if (is_resource($output)) @fclose($output);
        if ($temporary !== null) @unlink($temporary);
        @flock($lock, LOCK_UN);
        @fclose($lock);
    }
}
