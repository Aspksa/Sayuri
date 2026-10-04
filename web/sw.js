const CACHE='sayuri-ui-v1';
const SHELL=['/','/static/app.js','/static/assets/avatar.webp'];
self.addEventListener('install', event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate', event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch', event=>{
  const request=event.request;
  if(request.method!=='GET'||request.url.includes('/api/')) return;
  const url=new URL(request.url);
  if(url.origin!==self.location.origin) return;
  if(request.mode==='navigate') {
    event.respondWith(fetch(request).catch(()=>caches.match('/')));
  } else if(url.pathname==='/static/app.js'||url.pathname==='/static/assets/avatar.webp') {
    event.respondWith(fetch(request).then(response=>{
      if(response.ok){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(request,copy))}
      return response;
    }).catch(()=>caches.match(request)));
  }
});
