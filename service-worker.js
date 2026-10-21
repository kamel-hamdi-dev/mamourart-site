// Bump this version whenever a public resource changes.
// Separate format variants so a failed replacement cannot delete an active cache.
const PNG_BANNER = new URL(self.location.href).searchParams.get("banner") === "png";
const PNG_LOGO = new URL(self.location.href).searchParams.get("logo") === "png";
const CACHE_NAME = "mamourart-v9" + (PNG_BANNER ? "-png" : "") + (PNG_LOGO ? "-logo-png" : "");
const FILES_TO_CACHE = [
  "/", "/index.html", "/en.html", "/legal.html",
  "/gps-ai-demo.html", "/fret-alerts-demo.html",
  "/manifest.json",
  "/icon-192.png", "/icon-512.png", "/favicon.ico"
];
FILES_TO_CACHE.push(PNG_BANNER ? "/banner.png" : "/banner.webp", PNG_LOGO ? "/logo.png" : "/logo.webp");
const PUBLIC_PATHS = new Set(FILES_TO_CACHE.concat([
  "/dashboard.webp", "/gps-ai-preview.webp", "/fret-alerts-preview.webp",
  "/logo.webp", "/logo.png", "/banner.webp", "/banner.png", "/dashboard.png", "/apple-touch-icon.png",
  "/favicon-16x16.png", "/favicon-32x32.png", "/favicon-48x48.png", "/favicon-192.png"
]));
function isPublicUrl(url) {
  return url.origin === self.location.origin && !url.username && !url.password &&
    PUBLIC_PATHS.has(url.pathname) && !/\.php(?:\/|$)/i.test(url.pathname) &&
    [...url.searchParams].every(([key, value]) => key === "lang" && ["fr", "en"].includes(value));
}
function isCacheableResponse(response, url) {
  // A successful fetch alone does not make a response safe for Cache Storage.
  const networkUrl = new URL(url.href);
  networkUrl.hash = ""; // Fragments are not transmitted in HTTP requests.
  return isPublicUrl(url) && response.url === networkUrl.href && response.status === 200 &&
    response.type === "basic" && !response.redirected && !response.bodyUsed && response.body !== null &&
    !/no-store|private/i.test(response.headers.get("Cache-Control") || "") &&
    !response.headers.get("Vary")?.includes("*");
}
// Public resources have explicit contracts. Read a clone to completion before
// Cache.put; a non-null stream can still be empty, truncated or unreadable.
async function hasValidContent(response, url) {
  if (!isCacheableResponse(response, url)) return false;
  const path = url.pathname;
  const mime = (response.headers.get("Content-Type") || "").split(";")[0].trim().toLowerCase();
  const expected = path.endsWith(".webp") ? ["image/webp"] : path.endsWith(".png") ? ["image/png"] :
    path.endsWith(".ico") ? ["image/x-icon", "image/vnd.microsoft.icon"] :
    path.endsWith(".json") ? ["application/json", "application/manifest+json"] : ["text/html"];
  if (!expected.includes(mime)) return false;
  const limit = mime.startsWith("image/") ? 2 * 1024 * 1024 : 512 * 1024;
  const reader = response.clone().body.getReader();
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        // A tee's cancellation promise can wait for the original response's
        // consumer. Do not block validation on an unread original branch.
        reader.cancel().catch(() => {});
        return false;
      }
      chunks.push(value);
    }
    if (!size) return false;
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    if (mime.startsWith("image/")) {
      const ascii = (start, end) => String.fromCharCode(...bytes.subarray(start, end));
      if (path.endsWith(".webp") && (size < 12 || ascii(0, 4) !== "RIFF" || ascii(8, 12) !== "WEBP" ||
          new DataView(bytes.buffer).getUint32(4, true) + 8 !== size)) return false;
      if (path.endsWith(".png") && (size < 33 ||
          ![137,80,78,71,13,10,26,10].every((value, i) => bytes[i] === value) ||
          ascii(12, 16) !== "IHDR" || ascii(size - 8, size - 4) !== "IEND")) return false;
      if (path.endsWith(".ico")) {
        if (size < 22 || bytes[0] !== 0 || bytes[1] !== 0 || bytes[2] !== 1 || bytes[3] !== 0) return false;
        const view = new DataView(bytes.buffer), count = view.getUint16(4, true);
        if (!count || 6 + count * 16 > size) return false;
        for (let i = 0; i < count; i++) {
          const entry = 6 + i * 16, length = view.getUint32(entry + 8, true), offset = view.getUint32(entry + 12, true);
          if (!length || offset < 6 + count * 16 || offset + length > size) return false;
        }
      }
      // The real browser decoder catches corrupt payloads beyond magic bytes.
      const image = await createImageBitmap(new Blob([bytes], {type: mime}));
      const valid = image.width > 0 && image.height > 0;
      image.close();
      return valid;
    }
    const content = new TextDecoder("utf-8", {fatal: true}).decode(bytes);
    if (path.endsWith(".json")) {
      const manifest = JSON.parse(content);
      return manifest !== null && typeof manifest === "object" && !Array.isArray(manifest) &&
        typeof manifest.name === "string" && manifest.name.trim().length > 0 &&
        manifest.start_url === "/" && manifest.scope === "/" &&
        Array.isArray(manifest.icons) && manifest.icons.length > 0 &&
        manifest.icons.every(icon => typeof icon.src === "string" &&
          PUBLIC_PATHS.has(icon.src) && icon.type === "image/png");
    }
    // Structural HTML contract, not an HTML sanitizer or an authenticity check.
    return /^\s*<!doctype html>/i.test(content) && /<html\b[^>]*>/i.test(content) &&
      /<title\b[^>]*>[^<]+<\/title>/i.test(content) && /<body\b[^>]*>/i.test(content) &&
      /<\/body>\s*<\/html>\s*$/i.test(content);
  } catch (_) {
    return false;
  } finally {
    reader.releaseLock();
  }
}
async function discardCandidate(cache) {
  // Some storage failures also break CacheStorage.delete. Remove individual
  // entries as a second, bounded recovery path; never touch an older cache.
  try { if (await caches.delete(CACHE_NAME)) return; } catch (_) {}
  if (cache) {
    try {
      for (const request of await cache.keys()) await cache.delete(request).catch(() => {});
    } catch (_) {}
  }
  try { await caches.delete(CACHE_NAME); } catch (_) {}
}
async function verifyCandidate(cache) {
  const keys = await cache.keys();
  const expected = FILES_TO_CACHE.map(path => new URL(path, self.location.origin).href);
  if (keys.length !== expected.length || keys.some(key => !expected.includes(typeof key === "string" ? key : key.url))) {
    throw new Error("Incomplete precache candidate");
  }
  for (const url of expected) {
    const response = await cache.match(url);
    if (!response || !await hasValidContent(response, new URL(url))) throw new Error("Invalid stored precache response");
  }
}
async function installPrecache() {
  // Validate the complete essential set before any write. A failed candidate
  // rejects installation, leaving the active worker and its old cache intact.
  const candidates = await Promise.all(FILES_TO_CACHE.map(async path => {
    const url = new URL(path, self.location.origin);
    if (!path.startsWith("/") || path.startsWith("//") || !isPublicUrl(url) || url.search || url.hash) {
      throw new Error("Invalid public precache URL");
    }
    // The selected banner/logo were already loaded by the first page. Reuse
    // their HTTP cache entries, but validate their bodies just as strictly.
    const response = await fetch(url.href, {method: "GET", cache: /^\/(banner|logo)\./.test(path) ? "force-cache" : "no-cache", credentials: "same-origin", redirect: "error"});
    if (!await hasValidContent(response, url)) {
      response.body?.cancel().catch(() => {});
      throw new Error("Unsafe precache response");
    }
    return [url.href, response];
  }));
  let cache;
  try {
    cache = await caches.open(CACHE_NAME);
    // Recover residues from an earlier failed attempt. Never write into a
    // candidate whose old entries cannot be removed and verified absent.
    for (const request of await cache.keys()) await cache.delete(request);
    if ((await cache.keys()).length) throw new Error("Candidate cleanup incomplete");
    // Sequential writes ensure none can outlive failure cleanup.
    for (const [url, response] of candidates) await cache.put(url, response);
    await verifyCandidate(cache);
  } catch (error) {
    await discardCandidate(cache);
    throw error;
  }
  await self.skipWaiting();
}
self.addEventListener("install", event => {
  event.waitUntil(installPrecache());
});
self.addEventListener("activate", event => {
  event.waitUntil((async () => {
    // Check stored bytes before deleting any previously usable cache or claiming.
    await verifyCandidate(await caches.open(CACHE_NAME));
    const names = await caches.keys();
    await Promise.all(names.filter(name => /^mamourart-v\d+(?:-png)?(?:-logo-png)?$/.test(name) && name !== CACHE_NAME)
      .map(name => caches.delete(name)));
    await self.clients.claim();
  })());
});
self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Never intercept PHP, form results, unknown endpoints or sensitive queries.
  const isPublic = PUBLIC_PATHS.has(url.pathname);
  if (!isPublic && !(request.mode === "navigate" && /\.html$/.test(url.pathname))) return;
  const parameters = [...url.searchParams];
  const safeQuery = parameters.every(([key, value]) => key === "lang" && ["fr", "en"].includes(value));
  if (!safeQuery) return;
  const key = url.origin + url.pathname;
  event.respondWith((async () => {
    let cache;
    try { cache = await caches.open(CACHE_NAME); } catch (_) {}
    try {
      const response = await fetch(request, {cache: "no-cache"});
      // Preserve HTTP errors online. Do not cache redirects or private responses.
      if (isPublic && await hasValidContent(response, url)) {
        if (cache) await cache.put(key, response.clone()).catch(() => {});
      }
      return response;
    } catch (_) {
      const cached = cache ? await cache.match(key).catch(() => undefined) : undefined;
      if (cached) return cached;
      if (request.mode === "navigate") {
        const english = url.pathname === "/en.html" || url.searchParams.get("lang") === "en";
        return new Response(english
          ? '<!doctype html><html lang="en"><meta name="viewport" content="width=device-width"><title>Offline — Mamourart</title><h1>This page is unavailable offline</h1><p>Reconnect and try again.</p><a href="/en.html">Home</a></html>'
          : '<!doctype html><html lang="fr"><meta name="viewport" content="width=device-width"><title>Hors ligne — Mamourart</title><h1>Cette page est indisponible hors ligne</h1><p>Reconnectez-vous puis réessayez.</p><a href="/">Accueil</a></html>',
          {status: 503, headers: {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}});
      }
      return Response.error();
    }
  })());
});
