<?php
declare(strict_types=1);
namespace MamourartContactFaults;

// Only the namespaced COPY of the helper uses these fault injections.
function fopen(string $filename, string $mode) {
    if ($GLOBALS['contact_fault'] === 'open-write' && (str_contains($mode, 'w') || str_contains($mode, 'x'))) return false;
    if ($GLOBALS['contact_fault'] === 'open-lock' && basename($filename) === 'lock') return false;
    return \fopen($filename, $mode);
}
function mkdir(string $directory, int $permissions = 0777, bool $recursive = false): bool {
    return $GLOBALS['contact_fault'] === 'mkdir' ? false : \mkdir($directory, $permissions, $recursive);
}
function chmod(string $filename, int $permissions): bool {
    return $GLOBALS['contact_fault'] === 'chmod' ? false : \chmod($filename, $permissions);
}
function flock($stream, int $operation, &$would_block = null): bool {
    if ($GLOBALS['contact_fault'] === 'lock' && ($operation & LOCK_EX)) return false;
    return \flock($stream, $operation, $would_block);
}
function file_get_contents(string $filename, ...$args): string|false {
    return $GLOBALS['contact_fault'] === 'read' ? false : \file_get_contents($filename, ...$args);
}
function stream_get_contents($stream, ...$args): string|false {
    return $GLOBALS['contact_fault'] === 'read' ? false : \stream_get_contents($stream, ...$args);
}
function fread($stream, int $length): string|false {
    return $GLOBALS['contact_fault'] === 'read' ? false : \fread($stream, $length);
}
function fwrite($stream, string $data, ...$args): int|false {
    if ($GLOBALS['contact_fault'] === 'write') return false;
    if ($GLOBALS['contact_fault'] === 'write-zero') return 0;
    if ($GLOBALS['contact_fault'] === 'write-partial') {
        return $GLOBALS['contact_partial_written']++ === 0 ? \fwrite($stream, substr($data, 0, 1)) : false;
    }
    return \fwrite($stream, $data, ...$args);
}
function fflush($stream): bool {
    return $GLOBALS['contact_fault'] === 'flush' ? false : \fflush($stream);
}
function fclose($stream): bool {
    $result = \fclose($stream);
    if ($GLOBALS['contact_fault'] === 'close-lock') {
        $GLOBALS['contact_close_calls'] = ($GLOBALS['contact_close_calls'] ?? 0) + 1;
        if ($GLOBALS['contact_close_calls'] === 2) return false;
    }
    if ($GLOBALS['contact_fault'] === 'close' && !$GLOBALS['contact_close_failed']) {
        $GLOBALS['contact_close_failed'] = true;
        return false;
    }
    return $result;
}
function tempnam(string $directory, string $prefix): string|false {
    return $GLOBALS['contact_fault'] === 'temp' ? false : \tempnam($directory, $prefix);
}
function rename(string $from, string $to): bool {
    if ($GLOBALS['contact_fault'] === 'snapshot-rename' && !\is_dir($from) && basename($to) === 'state.json') return false;
    return $GLOBALS['contact_fault'] === 'rename' ? false : \rename($from, $to);
}

function unlink(string $path): bool {
    return $GLOBALS['contact_fault'] === 'unlink' ? false : \unlink($path);
}
function ftruncate($stream, int $size): bool {
    return $GLOBALS['contact_fault'] === 'truncate' ? false : \ftruncate($stream, $size);
}
