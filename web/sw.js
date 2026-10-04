// v4 removes old UI caches after the SAYURI BEYOND window separation.
const VERSION='sayuri-ui-v4';
self.addEventListener('install', event=>event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event=>event.waitUntil(
  caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('sayuri-ui-')).map(key=>caches.delete(key))))
    .then(()=>self.clients.claim())
));
// Do not intercept HTML, JavaScript, private API calls or auth responses.
// The user should always see the latest UI on restart.
