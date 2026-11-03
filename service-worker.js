const CACHE_NAME = "ward42-shell-v1";

const OFFLINE_URL = "/offline";

// FILES
const LOCAL_SHELL = [
    OFFLINE_URL,
    "/static/style.css",
    "/static/app.js",
    "/static/manifest.json",
    "/static/logo.svg",
    "/static/logo.svg",
];

// BOOTSTRAP
const CDN_SHELL = [
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css",
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js",
];

const NETWORK_TIMEOUT_MS = 8000;

// INSTALL 
self.addEventListener("install", (event) => {
    event.waitUntil(
        (async () => {
            const cache = await caches.open(CACHE_NAME);
            await cache.addAll(LOCAL_SHELL);

            await Promise.allSettled(
                CDN_SHELL.map((url) => cache.add(new Request(url, { mode: "cors" })))
            );

            await self.skipWaiting(); 
        })()
    );
});

// ACTIVATE 
self.addEventListener("activate", (event) => {
    event.waitUntil(
        (async () => {
            const names = await caches.keys();

            await Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name)));
            await self.clients.claim(); 
        })()
    );
});

// FETCH
function fetchWithTimeout(request) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), NETWORK_TIMEOUT_MS);
    return fetch(request, { signal: controller.signal }).finally(() => clearTimeout(timer));
}

//
function isShellAsset(url) {
    const sameOriginStatic = url.origin === self.location.origin && url.pathname.startsWith("/static/");
    return sameOriginStatic || CDN_SHELL.includes(url.href);
}

self.addEventListener("fetch", (event) => {
    const request = event.request;

    if (request.method !== "GET") return;

    if (request.headers.has("range")) return;

    const url = new URL(request.url);


    if (request.mode === "navigate") {
        event.respondWith(
            fetchWithTimeout(request).catch(async () => {
                const offlinePage = await caches.match(OFFLINE_URL);
                return offlinePage || new Response("You are offline.", { status: 503, headers: { "Content-Type": "text/plain" } });
            })
        );
        return;
    }

    if (isShellAsset(url)) {
        event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
        return;
    }

});
