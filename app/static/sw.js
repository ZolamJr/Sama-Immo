/* Service worker SamaImmo — coquille en cache pour le hors ligne.
   Stratégie : RÉSEAU D'ABORD pour l'application (fichiers minuscules) afin de
   toujours servir la dernière version quand on est en ligne, REPLI sur le
   cache quand la connexion est coupée. Les réponses API sont aussi mises en
   cache pour la consultation hors ligne. */
const VERSION = 'v1.2.0';
const SHELL = [
  '/', '/index.html', '/manifest.webmanifest',
  '/css/app.css',
  '/js/app.js', '/js/api.js', '/js/db.js', '/js/ui.js', '/js/format.js',
  '/js/views/login.js', '/js/views/accueil.js', '/js/views/encaisser.js',
  '/js/views/relances.js', '/js/views/biens.js', '/js/views/locataires.js',
  '/js/views/fiches.js', '/js/views/rapports.js', '/js/views/parametres.js',
  '/js/views/audit.js',
  '/icons/icon-192.png', '/icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open('shell-' + VERSION).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((cles) =>
      Promise.all(cles.filter((k) => k !== 'shell-' + VERSION && k !== 'api-' + VERSION)
        .map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) return;

  // API : réseau d'abord (données fraîches), repli sur le cache si coupé.
  if (url.pathname.startsWith('/api/')) {
    e.respondWith(
      fetch(e.request).then((rep) => {
        if (rep.ok && !url.pathname.startsWith('/api/public/')) {
          const copie = rep.clone();
          caches.open('api-' + VERSION).then((c) => c.put(e.request, copie));
        }
        return rep;
      }).catch(() =>
        caches.match(e.request).then((enCache) =>
          enCache || new Response(JSON.stringify({ erreur: 'hors-ligne', message: 'Aucune donnée en cache pour cette vue.' }),
            { status: 503, headers: { 'Content-Type': 'application/json' } })
        )
      )
    );
    return;
  }

  // Application (pages, JS, CSS, icônes) : réseau d'abord pour servir
  // systématiquement la dernière version, repli sur le cache hors ligne.
  e.respondWith(
    fetch(e.request).then((rep) => {
      if (rep.ok) {
        const copie = rep.clone();
        caches.open('shell-' + VERSION).then((c) => c.put(e.request, copie));
      }
      return rep;
    }).catch(() => caches.match(e.request))
  );
});
