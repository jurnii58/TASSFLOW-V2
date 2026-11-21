/**
 * TASSFLOW v2.0 - Service Worker Oficial para Notificaciones Web Push Nativas
 * Monitoreo Preventivo de Salud Ocupacional en Oficina (Referencia NOM-035-STPS-2018)
 */

const CACHE_NAME = 'tassflow-v2-sw-cache';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

// Escuchar eventos Push estándar del navegador
self.addEventListener('push', (event) => {
    let payload = {
        title: 'TASSFLOW v2.0 · Alerta Biométrica',
        body: 'Se ha detectado una anomalía en el monitoreo de salud ocupacional.',
        icon: '/static/icono.png',
        badge: '/static/icono.png',
        tag: 'tassflow-alert',
        requireInteraction: true,
        url: '/admin'
    };

    if (event.data) {
        try {
            const data = event.data.json();
            payload = Object.assign(payload, data);
        } catch (e) {
            payload.body = event.data.text();
        }
    }

    const options = {
        body: payload.body,
        icon: payload.icon || '/static/icono.png',
        badge: payload.badge || '/static/icono.png',
        tag: payload.tag || 'tassflow-alert',
        requireInteraction: payload.requireInteraction !== false,
        vibrate: [200, 100, 200],
        data: {
            url: payload.url || '/admin',
            nivel: payload.nivel || 2
        }
    };

    event.waitUntil(
        self.registration.showNotification(payload.title, options)
    );
});

// Permitir disparo directo desde el cliente WebSocket mediante postMessage
self.addEventListener('message', (event) => {
    if (!event.data || event.data.type !== 'SHOW_NATIVE_NOTIFICATION') return;

    const { title, body, tag, nivel, url } = event.data;
    const options = {
        body: body || 'Alerta preventiva NOM-035 en estación de trabajo.',
        icon: '/static/icono.png',
        badge: '/static/icono.png',
        tag: tag || `tassflow-nivel-${nivel || 2}-${Date.now()}`,
        requireInteraction: (nivel >= 2),
        vibrate: (nivel >= 3) ? [300, 100, 300, 100, 400] : [200, 100, 200],
        data: {
            url: url || '/admin',
            nivel: nivel || 2
        }
    };

    event.waitUntil(
        self.registration.showNotification(title || 'TASSFLOW v2.0', options)
    );
});

// Al hacer clic en la notificación nativa del sistema operativo, enfocar o abrir el panel
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.url) ? event.notification.data.url : '/admin';

    event.waitUntil(
        self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if (client.url.includes(targetUrl) && 'focus' in client) {
                    return client.focus();
                }
            }
            if (self.clients.openWindow) {
                return self.clients.openWindow(targetUrl);
            }
        })
    );
});
