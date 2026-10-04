// v3 removes old PWA HTML/JS caches that preserved obsolete chat menus.
const VERSION='sayuri-ui-v3';
self.addEventListener('install', event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event=>event.waitUntil(
  caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('sayuri-ui-')).map(key=>caches.delete(key))))
    .then(()=>self.clients.claim())
));
// Do not intercept HTML, JavaScript, private API calls or auth responses.
// The user should always see the latest UI on restart.
