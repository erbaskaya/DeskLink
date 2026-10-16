/**
 * DeskLink consent-based WebSocket relay logic.
 * Compatible with the v0.2 desktop.py JSON/JPEG protocol.
 * This is a relay, NOT end-to-end encryption: Cloudflare can access frames.
 */

export const MAX_FRAME_BYTES = 2_000_000;
const MAX_TEXT_CHARS = 2000;
const PENDING_MS = 30_000;
const RATE_WINDOW_MS = 600_000;
const RATE_LIMIT = 8;
const MAX_HOSTS = 5000;
const MAX_HOSTS_PER_IP = 16;
const MAX_BUFFERED_BYTES = 4_000_000;
const ID_PATTERN = /^[0-9]{9}$/;
const PIN_PATTERN = /^[0-9]{8}$/;
const DEVICE_KEY_PATTERN = /^[0-9a-f]{64}$/;
const DEVICE_NAME_MAX = 48;
const CONNECT_RATE_LIMIT = 20;

function safeName(input, fallback = 'Bilgisayar') {
  if (typeof input !== 'string') return fallback;
  const name = input.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, DEVICE_NAME_MAX);
  return name || fallback;
}

async function keyHash(key) {
  const bytes = new TextEncoder().encode(key);
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  return Array.from(digest, b => b.toString(16).padStart(2, '0')).join('');
}

function sameHash(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let different = 0;
  for (let i = 0; i < a.length; i++) different |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return different === 0;
}

function randomDigits9() {
  const data = new Uint32Array(1);
  crypto.getRandomValues(data);
  return String(100_000_000 + (data[0] % 900_000_000));
}

function randomToken() {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

function safeSend(ws, payload) {
  if (!ws || ws.readyState !== 1) return false;
  try {
    ws.send(typeof payload === 'string' || payload instanceof ArrayBuffer ? payload : JSON.stringify(payload));
    return true;
  } catch {
    return false;
  }
}

function validMeta(m) {
  const fields = ['left', 'top', 'width', 'height'];
  if (fields.some((k) => !Number.isInteger(m[k]))) return false;
  return m.left >= -100_000 && m.left <= 100_000 &&
    m.top >= -100_000 && m.top <= 100_000 &&
    m.width >= 1 && m.width <= 16_384 && m.height >= 1 && m.height <= 16_384;
}

function validInput(m) {
  if (m.kind === 'mouse_move') {
    return Number.isFinite(m.x) && Number.isFinite(m.y) &&
      m.x >= 0 && m.x <= 1 && m.y >= 0 && m.y <= 1;
  }
  if (m.kind === 'mouse_button') {
    return ['left', 'right', 'middle'].includes(m.button) && ['down', 'up'].includes(m.action);
  }
  if (m.kind === 'scroll') return Number.isInteger(m.delta) && m.delta >= -10 && m.delta <= 10;
  if (m.kind === 'key') {
    return typeof m.key === 'string' && m.key.length >= 1 && m.key.length <= 32 &&
      [...m.key].every((c) => c >= ' ' && c !== '\x7f') &&
      (m.char === undefined || (typeof m.char === 'string' && m.char.length <= 1)) &&
      ['down', 'up'].includes(m.action);
  }
  return m.kind === 'release_all';
}

export class RelayHub {
  constructor(ctx) {
    this.ctx = ctx;
    this.hosts = new Map();        // 9-digit ID -> {ws, pin (legacy only), mode, ip, viewer, pending}
    this.viewers = new Map();      // websocket -> {hostId, state, token, expiresAt}
    // Rebuild sessions from attachment metadata after a Durable Object hibernates.
    const recovered = ctx.getWebSockets();
    for (const ws of recovered) {
      const meta = ws.deserializeAttachment();
      if (meta?.role !== 'host' || !ID_PATTERN.test(meta.id || '')) continue;
      const persistent = meta.mode === 'persistent';
      if (!persistent && !PIN_PATTERN.test(meta.pin || '')) continue;
      if (!this.hosts.has(meta.id)) {
        this.hosts.set(meta.id, {ws, pin: persistent ? null : meta.pin,
          mode: persistent ? 'persistent' : 'legacy', name: safeName(meta.name),
          ip: meta.ip || 'unknown', viewer: null, pending: null});
      }
    }
    for (const ws of recovered) {
      const meta = ws.deserializeAttachment();
      if (meta?.role !== 'viewer' || !this.hosts.has(meta.hostId)) continue;
      if (meta.state !== 'active' && meta.state !== 'pending') continue;
      const host = this.hosts.get(meta.hostId);
      if (host[meta.state === 'active' ? 'viewer' : 'pending'] != null) continue;
      const link = {
        hostId: meta.hostId, state: meta.state,
        token: meta.token || '', expiresAt: meta.expiresAt || 0,
      };
      this.viewers.set(ws, link);
      host[meta.state === 'active' ? 'viewer' : 'pending'] = ws;
    }
  }

  // Called by the Cloudflare Durable Object when a new desktop connection opens.
  acceptSocket(ws, ip = 'unknown') {
    this.ctx.acceptWebSocket(ws); // WebSocket hibernation, NOT socket.accept().
    ws.serializeAttachment({role: 'guest', ip: String(ip).slice(0, 64)});
  }

  async alarm() {
    const now = Date.now();
    for (const [ws, link] of [...this.viewers]) {
      if (link.state === 'pending' && link.expiresAt <= now) {
        this.leaveViewer(ws, {notice: {type: 'error', message: 'İzin isteğinin süresi doldu.'}});
      }
    }
    let next = Infinity;
    for (const link of this.viewers.values()) {
      if (link.state === 'pending') next = Math.min(next, link.expiresAt);
    }
    const stored = await this.ctx.storage.list({prefix: 'rate:'});
    for (const [key, record] of stored) {
      if (!record || record.expiresAt <= now) await this.ctx.storage.delete(key);
      else next = Math.min(next, record.expiresAt);
    }
    if (Number.isFinite(next)) await this.ctx.storage.setAlarm(next);
  }

  async earlierAlarm(deadline) {
    const scheduled = await this.ctx.storage.getAlarm();
    if (scheduled === null || scheduled > deadline) {
      await this.ctx.storage.setAlarm(deadline);
    }
  }

  async tooManyAttempts(ip) {
    const r = await this.ctx.storage.get(`rate:${ip}`);
    return !!r && r.expiresAt > Date.now() && r.count >= RATE_LIMIT;
  }

  async failedAttempt(ip) {
    const key = `rate:${ip}`;
    const now = Date.now();
    let r = await this.ctx.storage.get(key);
    if (!r || r.expiresAt <= now) r = {count: 0, expiresAt: now + RATE_WINDOW_MS};
    r.count += 1;
    await this.ctx.storage.put(key, r);
    await this.earlierAlarm(r.expiresAt);
  }

  async webSocketMessage(ws, message) {
    const meta = ws.deserializeAttachment() || {role: 'guest', ip: 'unknown'};
    if (message instanceof ArrayBuffer) {
      // Only approved hosts may stream JPEG. Avoid buffering slow viewers.
      const host = meta.role === 'host' ? this.hosts.get(meta.id) : null;
      if (!host || host.ws !== ws || !host.viewer) return;
      const u8 = new Uint8Array(message);
      if (u8.byteLength < 4 || u8.byteLength > MAX_FRAME_BYTES ||
          u8[0] !== 0xff || u8[1] !== 0xd8 ||
          u8[u8.length - 2] !== 0xff || u8[u8.length - 1] !== 0xd9) return;
      if ((host.viewer.bufferedAmount || 0) > MAX_BUFFERED_BYTES) return;
      if (!safeSend(host.viewer, message)) this.leaveViewer(host.viewer);
      return;
    }
    if (typeof message !== 'string' || message.length > MAX_TEXT_CHARS) {
      safeSend(ws, {type: 'error', message: 'Geçersiz mesaj.'});
      return;
    }
    let msg;
    try { msg = JSON.parse(message); } catch { safeSend(ws, {type:'error',message:'Geçersiz JSON.'}); return; }
    if (!msg || typeof msg !== 'object' || Array.isArray(msg)) return;
    const action = msg.type;

    if (meta.role === 'guest' && action === 'register') {
      if (this.hosts.size >= MAX_HOSTS || [...this.hosts.values()].filter(h => h.ip === meta.ip).length >= MAX_HOSTS_PER_IP) {
        safeSend(ws, {type: 'error', message: 'Sunucu veya cihaz bağlantı sınırı dolu.'}); return;
      }
      // New registration: the 9-digit ID is generated once by the desktop
      // client. Durable Object storage binds it to a 256-bit device secret.
      if (msg.device_id !== undefined || msg.device_key !== undefined) {
        const id = msg.device_id;
        const key = msg.device_key;
        if (typeof id !== 'string' || !ID_PATTERN.test(id) ||
            typeof key !== 'string' || !DEVICE_KEY_PATTERN.test(key)) {
          safeSend(ws, {type:'error', message:'Geçersiz cihaz kimliği.'}); return;
        }
        if (this.hosts.has(id)) {
          safeSend(ws, {type:'error',message:'Bu ID başka bir aktif oturumda. Diğer DeskLink uygulamasını kapatın.'}); return;
        }
        if (await this.tooManyAttempts(meta.ip)) {
          safeSend(ws,{type:'error',message:'Çok fazla kimlik denemesi.'});return;
        }
        const digest = await keyHash(key);
        const storageKey = `device:${id}`;
        const previous = await this.ctx.storage.get(storageKey);
        if (previous && !sameHash(previous.hash, digest)) {
          await this.failedAttempt(meta.ip);
          safeSend(ws, {type:'id_conflict'}); return;
        }
        const name = safeName(msg.name);
        if (!previous) {
          const rateKey = `rate:enroll:${meta.ip}`;
          const now = Date.now();
          const previousRate = await this.ctx.storage.get(rateKey);
          const rate = previousRate && previousRate.expiresAt > now
            ? {...previousRate,count:previousRate.count+1}
            : {count:1,expiresAt:now+RATE_WINDOW_MS};
          if (rate.count > 30) {
            safeSend(ws,{type:'error',message:'Çok fazla yeni cihaz kaydı; sonra tekrar deneyin.'});return;
          }
          await this.ctx.storage.put(rateKey,rate);
          await this.earlierAlarm(rate.expiresAt);
          await this.ctx.storage.put(storageKey, {hash: digest, name});
        }
        else if (previous.name !== name) await this.ctx.storage.put(storageKey, {...previous, name});
        const host = {ws, pin:null, mode:'persistent', name, ip:meta.ip, viewer:null, pending:null};
        this.hosts.set(id, host);
        // Do not store plaintext device_key in socket attachment.
        ws.serializeAttachment({role:'host', mode:'persistent', id, name, ip:meta.ip});
        safeSend(ws, {type:'registered',id});
        return;
      }
      // Old clients can still connect using the legacy 8-digit code until upgraded.
      if (typeof msg.pin !== 'string' || !PIN_PATTERN.test(msg.pin)) {
        safeSend(ws, {type:'error',message:'Eski sürüm için 8 haneli PIN gerekli.'}); return;
      }
      let id = '';
      for (let i = 0; i < 30; i++) {
        id = randomDigits9();
        if (!this.hosts.has(id) && !await this.ctx.storage.get(`device:${id}`)) break;
      }
      if (this.hosts.has(id) || await this.ctx.storage.get(`device:${id}`)) {
        safeSend(ws, {type:'error',message:'Yeni ID üretilemedi.'});return;
      }
      const host = {ws, pin:msg.pin, mode:'legacy', name:'Eski DeskLink', ip:meta.ip, viewer:null, pending:null};
      this.hosts.set(id, host);
      ws.serializeAttachment({role:'host',mode:'legacy',id,pin:msg.pin,name:host.name,ip:meta.ip});
      safeSend(ws, {type:'registered',id});
      return;
    }

    // Verify the caller owns a saved identity. This prevents a remote user from
    // simply typing another person's 9-digit ID into the requester label.
    if (meta.role === 'guest' && action === 'identify') {
      if (await this.tooManyAttempts(meta.ip)) {
        safeSend(ws,{type:'error',message:'Çok fazla deneme. Daha sonra tekrar deneyin.'});return;
      }
      const id = msg.device_id;
      const key = msg.device_key;
      if (typeof id !== 'string' || !ID_PATTERN.test(id) ||
          typeof key !== 'string' || !DEVICE_KEY_PATTERN.test(key)) {
        await this.failedAttempt(meta.ip);
        safeSend(ws,{type:'error',message:'Geçersiz cihaz kimliği.'});return;
      }
      const record = await this.ctx.storage.get(`device:${id}`);
      const digest = await keyHash(key);
      if (!record || !sameHash(record.hash, digest)) {
        await this.failedAttempt(meta.ip);
        safeSend(ws,{type:'error',message:'Cihaz kimliği sunucuda doğrulanamadı.'});return;
      }
      ws.serializeAttachment({role:'identified', ip:meta.ip, id, name:safeName(record.name)});
      safeSend(ws,{type:'identified',id});
      return;
    }

    if ((meta.role === 'guest' || meta.role === 'identified') && action === 'connect') {
      if (await this.tooManyAttempts(meta.ip)) {
        safeSend(ws, {type:'error',message:'Çok fazla deneme. 10 dakika sonra tekrar deneyin.'});return;
      }
      const hostId = msg.id;
      const pin = msg.pin;
      if (typeof hostId !== 'string' || !ID_PATTERN.test(hostId)) {
        await this.failedAttempt(meta.ip);
        safeSend(ws,{type:'error',message:'9 haneli bilgisayar ID hatalı.'});return;
      }
      const host = this.hosts.get(hostId);
      if (!host) {
        await this.failedAttempt(meta.ip);
        safeSend(ws,{type:'error',message:'Bilgisayar çevrimdışı veya ID yanlış.'});return;
      }
      if (host.mode === 'persistent' && meta.role !== 'identified') {
        await this.failedAttempt(meta.ip);
        safeSend(ws,{type:'error',message:'DeskLink 0.5 veya üstü gerekli.'});return;
      }
      if (host.mode === 'legacy' && (typeof pin !== 'string' || !PIN_PATTERN.test(pin) || host.pin !== pin)) {
        await this.failedAttempt(meta.ip);
        safeSend(ws,{type:'error',message:'Bu bilgisayarda yeni DeskLink sürümü kurulmalı.'});return;
      }
      if (host.viewer || host.pending) {
        safeSend(ws,{type:'error',message:'Karşı bilgisayar meşgul.'});return;
      }
      // Cap legitimate connection-notification frequency too; a known ID is
      // not an invitation to spam the owner with popups.
      const key = `rate:request:${meta.ip}`;
      const now = Date.now();
      const r = await this.ctx.storage.get(key);
      if (r && r.expiresAt > now && r.count >= CONNECT_RATE_LIMIT) {
        safeSend(ws,{type:'error',message:'Çok fazla bağlantı isteği. Daha sonra tekrar deneyin.'});return;
      }
      const next = r && r.expiresAt > now ? {...r, count:r.count + 1} : {count:1,expiresAt:now+RATE_WINDOW_MS};
      await this.ctx.storage.put(key,next);
      await this.earlierAlarm(next.expiresAt);
      const token = randomToken();
      const expiresAt = Date.now() + PENDING_MS;
      const link = {hostId,state:'pending',token,expiresAt};
      host.pending = ws;
      this.viewers.set(ws,link);
      ws.serializeAttachment({role:'viewer',ip:meta.ip, ...link});
      safeSend(ws,{type:'pending'});
      const requester_id = meta.role === 'identified' ? meta.id : '';
      const requester_name = meta.role === 'identified' ? meta.name : 'Kimliği doğrulanmamış eski istemci';
      if (!safeSend(host.ws,{type:'connection_request',token,requester_id,requester_name})) {
        this.leaveViewer(ws,{notice:{type:'closed',reason:'Bilgisayar çevrimdışı.'}});return;
      }
      await this.earlierAlarm(expiresAt);
      return;
    }

    if (meta.role === 'host') {
      const host = this.hosts.get(meta.id);
      if (!host || host.ws !== ws) return;
      if (action === 'approve') {
        const guest = host.pending;
        const link = guest && this.viewers.get(guest);
        if (!link || link.token !== msg.token) return;
        if (link.expiresAt <= Date.now()) {
          this.leaveViewer(guest, {notice:{type:'error',message:'İzin isteğinin süresi doldu.'}});return;
        }
        if (msg.accept === true) {
          host.pending = null;
          host.viewer = guest;
          link.state = 'active';
          link.token = '';
          link.expiresAt = 0;
          const gmeta = guest.deserializeAttachment() || {};
          guest.serializeAttachment({role:'viewer',ip:gmeta.ip,...link});
          if (!safeSend(guest,{type:'accepted',id:meta.id,name:host.name})) {this.leaveViewer(guest);return;}
          safeSend(ws,{type:'viewer_connected'});
        } else {
          this.leaveViewer(guest,{notice:{type:'rejected'}});
        }
        return;
      }
      if (action === 'frame_meta') {
        if (host.viewer && validMeta(msg)) safeSend(host.viewer, msg);
        return;
      }
      if (action === 'disconnect') {
        if (host.viewer) this.leaveViewer(host.viewer, {notice:{type:'closed',reason:'Karşı bilgisayar bağlantıyı sonlandırdı.'}, notifyHost:false});
        if (host.pending) this.leaveViewer(host.pending,{notice:{type:'rejected'},notifyHost:false});
        return;
      }
    }

    if (meta.role === 'viewer') {
      const link = this.viewers.get(ws);
      const host = link && this.hosts.get(link.hostId);
      if (!link || !host) return;
      if (action === 'disconnect') {
        this.leaveViewer(ws, {notice:{type:'closed'}});
      } else if (action === 'input' && link.state === 'active' && validInput(msg)) {
        if (!safeSend(host.ws,msg)) this.leaveViewer(ws,{notice:{type:'closed',reason:'Bilgisayar çevrimdışı.'}});
      }
      return;
    }
    safeSend(ws, {type:'error',message:'Beklenmeyen istek.'});
  }

  leaveViewer(ws, {notice = null, notifyHost = true} = {}) {
    const link = this.viewers.get(ws);
    if (!link) return;
    this.viewers.delete(ws);
    const host = this.hosts.get(link.hostId);
    if (host) {
      if (link.state === 'pending' && host.pending === ws) {
        host.pending = null;
        if (notifyHost) safeSend(host.ws,{type:'request_canceled'});
      }
      if (link.state === 'active' && host.viewer === ws) {
        host.viewer = null;
        if (notifyHost) safeSend(host.ws,{type:'viewer_left'});
      }
    }
    const prev = ws.deserializeAttachment() || {};
    ws.serializeAttachment({role:'guest',ip:prev.ip || 'unknown'});
    if (notice) safeSend(ws,notice);
  }

  webSocketClose(ws) {
    const meta = ws.deserializeAttachment() || {};
    if (meta.role === 'host') {
      const host = this.hosts.get(meta.id);
      if (host && host.ws === ws) {
        // Notify visitors before unregistering the host.
        if (host.viewer) this.leaveViewer(host.viewer,{notice:{type:'closed',reason:'Bilgisayar çevrimdışı.'},notifyHost:false});
        if (host.pending) this.leaveViewer(host.pending,{notice:{type:'closed',reason:'Bilgisayar çevrimdışı.'},notifyHost:false});
        this.hosts.delete(meta.id);
      }
    } else if (meta.role === 'viewer') {
      this.leaveViewer(ws);
    }
  }

  webSocketError(ws) { this.webSocketClose(ws); }
}
