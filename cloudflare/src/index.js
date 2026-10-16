import { DurableObject } from 'cloudflare:workers';
import { RelayHub } from './hub.js';

export class DeskLinkHub extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.hub = new RelayHub(ctx);
  }

  fetch(request) {
    if (request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') {
      return new Response('WebSocket gerekli.', {status: 426});
    }
    const pair = new WebSocketPair();
    const [client, server] = Object.values(pair);
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    this.hub.acceptSocket(server, ip);
    return new Response(null, {status: 101, webSocket: client});
  }

  webSocketMessage(ws, message) { return this.hub.webSocketMessage(ws, message); }
  webSocketClose(ws) { return this.hub.webSocketClose(ws); }
  webSocketError(ws, error) { return this.hub.webSocketError(ws, error); }
  alarm() { return this.hub.alarm(); }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/' && request.method === 'GET' && request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') {
      return Response.json({
        application: 'DeskLink Cloudflare Relay',
        version: '0.5.0',
        status: 'ok',
        websocket: `wss://${url.host}/ws`,
        note: 'Bu adres masaustu DeskLink uygulamasinda kullanilir. Parola veya ID bu sayfaya yazilmaz.',
      }, {headers:{'cache-control':'no-store'}});
    }
    if (!['/ws', '/'].includes(url.pathname)) return new Response('Bulunamadı.', {status:404});
    if (request.headers.get('Upgrade')?.toLowerCase() !== 'websocket') {
      return new Response('WebSocket baglantisi gerekli.', {status: 426});
    }
    // This relay is intended for installed Windows/macOS clients, not websites.
    if (request.headers.has('Origin')) return new Response('Tarayici baglantisi desteklenmiyor.', {status:403});
    if (request.method !== 'GET') return new Response('Method not allowed', {status:405});
    const id = env.DESKLINK_HUB.idFromName('single-hub-v1');
    return env.DESKLINK_HUB.get(id).fetch(request);
  },
};
