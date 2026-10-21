// Bump this version whenever a public resource changes.
const CACHE_NAME = "mamourart-v6";
const FILES_TO_CACHE = [
  "/", "/index.html", "/en.html", "/legal.html",
  "/gps-ai-demo.html", "/fret-alerts-demo.html",
  "/logo.webp", "/banner.webp", "/manifest.json",
  "/icon-192.png", "/icon-512.png", "/favicon.ico"
];
const PUBLIC_PATHS = new Set(FILES_TO_CACHE.concat([
  "/dashboard.webp", "/gps-ai-preview.webp", "/fret-alerts-preview.webp",
  "/logo.png", "/banner.png", "/dashboard.png", "/apple-touch-icon.png",
  "/favicon-16x16.png", "/favicon-32x32.png", "/favicon-48x48.png", "/favicon-192.png"
]));
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(FILES_TO_CACHE))
    .then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(names => Promise.all(names
    .filter(name => /^mamourart-v\d+$/.test(name) && name !== CACHE_NAME)
    .map(name => caches.delete(name)))).then(() => self.clients.claim()));
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
      if (isPublic && response.status === 200 && response.type === "basic" && !response.redirected &&
          !/no-store|private/i.test(response.headers.get("Cache-Control") || "") &&
          !response.headers.get("Vary")?.includes("*")) {
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
