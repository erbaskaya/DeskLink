import test from 'node:test';
import assert from 'node:assert/strict';
import {RelayHub} from '../src/hub.js';

class FakeSocket {
  constructor(ip = '203.0.113.1') {
    this.messages = [];
    this.readyState = 1;
    this.bufferedAmount = 0;
    this.meta = {role:'guest',ip};
  }
  send(msg) { this.messages.push(typeof msg === 'string' ? JSON.parse(msg) : msg); }
  serializeAttachment(m) {this.meta = structuredClone(m);}
  deserializeAttachment() {return this.meta;}
  last() {return this.messages.at(-1);}
}
class FakeStorage {
  constructor() {this.kv=new Map();this.alarmTime=null;}
  async get(k) {return this.kv.get(k);}
  async put(k,v) {this.kv.set(k,structuredClone(v));}
  async delete(k) {this.kv.delete(k);}
  async list({prefix}) {return new Map([...this.kv].filter(([k])=>k.startsWith(prefix)));}
  async getAlarm() {return this.alarmTime;}
  async setAlarm(t) {this.alarmTime=t;}
}
class FakeContext {
  constructor() {this.sockets=[];this.storage=new FakeStorage();}
  acceptWebSocket(ws) {this.sockets.push(ws);}
  getWebSockets() {return this.sockets.filter(s=>s.readyState===1);}
}
function rig(){const ctx=new FakeContext();const hub=new RelayHub(ctx);return {ctx,hub};}
function add(hub,ip){const s=new FakeSocket(ip);hub.acceptSocket(s,ip);return s;}
async function register(hub,ws,pin='12345678'){
  await hub.webSocketMessage(ws,JSON.stringify({type:'register',pin}));
  assert.equal(ws.last().type,'registered');
  assert.match(ws.last().id,/^[0-9]{9}$/);
  return ws.last().id;
}
async function connect(hub,ws,id,pin='12345678') {
  await hub.webSocketMessage(ws,JSON.stringify({type:'connect',id,pin}));
}
async function approvedPair() {
  const {hub,ctx}=rig();
  const host=add(hub,'203.0.113.1');
  const viewer=add(hub,'203.0.113.2');
  const id=await register(hub,host);
  await connect(hub,viewer,id);
  const token=host.last().token;
  await hub.webSocketMessage(host,JSON.stringify({type:'approve',token,accept:true}));
  return {hub,ctx,host,viewer,id};
}

test('guest registration has a random ID; cannot register twice',async()=>{
  const {hub}=rig();const a=add(hub,'a');
  const id=await register(hub,a);
  await hub.webSocketMessage(a,JSON.stringify({type:'register',pin:'12345678'}));
  assert.equal(a.last().type,'error');
  assert.equal(hub.hosts.size,1);
  assert.equal(hub.hosts.has(id),true);
});

test('invalid pin and wrong ID do not start requests',async()=>{
  const {hub}=rig();const h=add(hub,'a');const v=add(hub,'b');
  await hub.webSocketMessage(h,JSON.stringify({type:'register',pin:'12'}));
  assert.equal(h.last().type,'error');
  const id=await register(hub,h);
  await connect(hub,v,id,'87654321');
  assert.equal(v.last().type,'error');
  assert.equal(h.last().type,'registered');
});

test('explicit approval is mandatory; relay forwards JPEG and input after approval',async()=>{
  const {hub}=rig();const host=add(hub,'h');const v=add(hub,'v');
  const id=await register(hub,host);
  await connect(hub,v,id);
  assert.equal(v.last().type,'pending');
  assert.equal(host.last().type,'connection_request');
  const token=host.last().token;
  const jpeg=new Uint8Array([255,216,1,2,3,255,217]).buffer;
  await hub.webSocketMessage(host,jpeg);
  assert.notEqual(v.last(),jpeg);
  await hub.webSocketMessage(v,JSON.stringify({type:'input',kind:'mouse_move',x:0.3,y:0.6}));
  assert.equal(host.last().type,'connection_request');
  await hub.webSocketMessage(host,JSON.stringify({type:'approve',token,accept:true}));
  assert.equal(v.last().type,'accepted');
  assert.equal(host.last().type,'viewer_connected');
  await hub.webSocketMessage(host,jpeg);
  assert.equal(v.last(),jpeg);
  await hub.webSocketMessage(v,JSON.stringify({type:'input',kind:'mouse_move',x:0.3,y:0.6}));
  assert.equal(host.last().kind,'mouse_move');
  assert.equal(host.last().x,0.3);
});

test('host can reject and viewer is informed',async()=>{
  const {hub}=rig();const h=add(hub,'h');const v=add(hub,'v');
  const id=await register(hub,h);await connect(hub,v,id);
  const token=h.last().token;
  await hub.webSocketMessage(h,JSON.stringify({type:'approve',token,accept:false}));
  assert.equal(v.last().type,'rejected');
  assert.equal(hub.viewers.size,0);
});

test('backpressure drops frames and invalid JPEGs are rejected',async()=>{
  const {hub,host,viewer}=await approvedPair();
  viewer.bufferedAmount=5_000_000;
  const jpg=new Uint8Array([255,216,5,9,255,217]).buffer;
  await hub.webSocketMessage(host,jpg);
  assert.equal(viewer.last().type,'accepted');
  viewer.bufferedAmount=0;
  await hub.webSocketMessage(host,new Uint8Array([2,3,4]).buffer);
  assert.equal(viewer.last().type,'accepted');
  await hub.webSocketMessage(host,jpg);
  assert.equal(viewer.last(),jpg);
});

test('host and guest session cleanup does not unregister host on remote stop',async()=>{
  const {hub,host,viewer,id}=await approvedPair();
  await hub.webSocketMessage(host,JSON.stringify({type:'disconnect'}));
  assert.equal(viewer.last().type,'closed');
  assert.equal(hub.hosts.has(id),true);
  assert.equal(hub.viewers.size,0);
  const next=add(hub,'new');
  await connect(hub,next,id);
  assert.equal(next.last().type,'pending');
  hub.webSocketClose(host);
  assert.equal(next.last().type,'closed');
  assert.equal(hub.hosts.has(id),false);
});

test('viewer disconnect notifies host',async()=>{
  const {hub,host,viewer}=await approvedPair();
  hub.webSocketClose(viewer);
  assert.equal(host.last().type,'viewer_left');
});

test('hibernation reconstructs active pair from socket attachments',async()=>{
  const {hub,ctx,host,viewer}=await approvedPair();
  const afterWake=new RelayHub(ctx);
  assert.equal(afterWake.hosts.size,1);
  assert.equal(afterWake.viewers.size,1);
  await afterWake.webSocketMessage(host,new Uint8Array([255,216,9,255,217]).buffer);
  assert.equal(new Uint8Array(viewer.last())[2],9);
});

test('hibernation reconstructs pending pair and approval token',async()=>{
  const {hub,ctx}=rig();const h=add(hub,'h');const v=add(hub,'v');
  const id=await register(hub,h);await connect(hub,v,id);
  const token=h.last().token;
  const afterWake=new RelayHub(ctx);
  await afterWake.webSocketMessage(h,JSON.stringify({type:'approve',token,accept:true}));
  assert.equal(v.last().type,'accepted');
});

test('pending request expires via durable object alarm',async()=>{
  const {hub}=rig();const h=add(hub,'h');const v=add(hub,'v');
  const id=await register(hub,h);await connect(hub,v,id);
  const link=hub.viewers.get(v);link.expiresAt=Date.now()-1;
  await hub.alarm();
  assert.equal(v.last().type,'error');
  assert.equal(h.last().type,'request_canceled');
});

test('too many wrong access codes triggers blocking with persistent storage',async()=>{
  const {hub,ctx}=rig();const v=add(hub,'ip');
  for(let i=0;i<8;i++) await connect(hub,v,'999999999','00000000');
  await connect(hub,v,'999999999','00000000');
  assert.match(v.last().message,/Çok fazla deneme/);
  const afterWake=new RelayHub(ctx);
  await connect(afterWake,v,'999999999','00000000');
  assert.match(v.last().message,/Çok fazla deneme/);
});

test('valid frame metadata forwarded, malformed remote-control actions are rejected',async()=>{
  const {hub,host,viewer}=await approvedPair();
  await hub.webSocketMessage(host,JSON.stringify({type:'frame_meta',left:0,top:0,width:1920,height:1080}));
  assert.equal(viewer.last().type,'frame_meta');
  const before=host.messages.length;
  await hub.webSocketMessage(viewer,JSON.stringify({type:'input',kind:'mouse_move',x:45,y:0.3}));
  assert.equal(host.messages.length,before);
  await hub.webSocketMessage(viewer,JSON.stringify({type:'input',kind:'key',key:'a',action:'down'}));
  assert.equal(host.last().kind,'key');
});

const KEY_A = 'a'.repeat(64);
const KEY_B = 'b'.repeat(64);
const KEY_C = 'c'.repeat(64);
async function registerPersistent(hub, ws, id='123456789', key=KEY_A, name='Windows bilgisayar') {
  await hub.webSocketMessage(ws, JSON.stringify({type:'register',device_id:id,device_key:key,name}));
  return ws.last();
}
async function identify(hub, ws, id='987654321', key=KEY_B) {
  await hub.webSocketMessage(ws, JSON.stringify({type:'identify',device_id:id,device_key:key}));
  return ws.last();
}

test('persistent ID belongs to one device secret and reconnects with same ID',async()=>{
  const {hub,ctx}=rig();
  const h=add(hub,'11.0.0.1');
  assert.deepEqual(await registerPersistent(hub,h),{type:'registered',id:'123456789'});
  assert.equal((await ctx.storage.get('device:123456789')).hash.length,64);
  assert.equal((await ctx.storage.get('device:123456789')).hash.includes(KEY_A),false);
  hub.webSocketClose(h);h.readyState=3;
  const wrong=add(hub,'22.0.0.2');
  assert.equal((await registerPersistent(hub,wrong,'123456789',KEY_C)).type,'id_conflict');
  const returned=add(hub,'11.0.0.3');
  assert.deepEqual(await registerPersistent(hub,returned),{type:'registered',id:'123456789'});
});

test('ID-only connection notifies the target only after caller identity verification',async()=>{
  const {hub}=rig();
  const host=add(hub,'1.1.1.1');const callerHost=add(hub,'2.2.2.2');
  const viewer=add(hub,'2.2.2.2');const anonymous=add(hub,'3.3.3.3');
  await registerPersistent(hub,host,'123456789',KEY_A,'Mac bilgisayar');
  await registerPersistent(hub,callerHost,'987654321',KEY_B,'Windows bilgisayar');
  await hub.webSocketMessage(anonymous,JSON.stringify({type:'connect',id:'123456789'}));
  assert.equal(anonymous.last().type,'error');
  assert.equal(host.last().type,'registered');
  const beforeIdentify=await identify(hub,viewer,'987654321',KEY_C);
  assert.equal(beforeIdentify.type,'error');
  assert.equal((await identify(hub,viewer)).type,'identified');
  await hub.webSocketMessage(viewer,JSON.stringify({type:'connect',id:'123456789'}));
  assert.equal(viewer.last().type,'pending');
  assert.equal(host.last().type,'connection_request');
  assert.equal(host.last().requester_id,'987654321');
  assert.equal(host.last().requester_name,'Windows bilgisayar');
  assert.match(host.last().token,/^[a-f0-9]{24}$/);
  await hub.webSocketMessage(host,JSON.stringify({type:'approve',token:host.last().token,accept:true}));
  assert.equal(viewer.last().type,'accepted');
  assert.equal(viewer.last().name,'Mac bilgisayar');
  assert.equal(viewer.last().id,'123456789');
  await hub.webSocketMessage(viewer,JSON.stringify({type:'input',kind:'mouse_move',x:0.3,y:0.6}));
  assert.equal(host.last().kind,'mouse_move');
});

test('declining a saved ID-only request never grants remote input',async()=>{
  const {hub}=rig();const host=add(hub,'1.1.1.1');const caller=add(hub,'2.2.2.2');const viewer=add(hub,'2.2.2.3');
  await registerPersistent(hub,host,'123456789',KEY_A);
  await registerPersistent(hub,caller,'987654321',KEY_B);
  await identify(hub,viewer);
  await hub.webSocketMessage(viewer,JSON.stringify({type:'connect',id:'123456789'}));
  const token=host.last().token;
  await hub.webSocketMessage(viewer,JSON.stringify({type:'input',kind:'key',key:'a',action:'down'}));
  assert.equal(host.last().type,'connection_request');
  await hub.webSocketMessage(host,JSON.stringify({type:'approve',token,accept:false}));
  assert.equal(viewer.last().type,'rejected');
  assert.equal(hub.hosts.get('123456789').viewer,null);
});

test('hibernation reconstructs persistent hosts and pending requests',async()=>{
  const {hub,ctx}=rig();const host=add(hub,'1.1.1.1');const caller=add(hub,'2.2.2.2');const viewer=add(hub,'2.2.2.3');
  await registerPersistent(hub,host,'123456789',KEY_A);
  await registerPersistent(hub,caller,'987654321',KEY_B);
  await identify(hub,viewer);
  await hub.webSocketMessage(viewer,JSON.stringify({type:'connect',id:'123456789'}));
  const token=host.last().token;
  const afterWake=new RelayHub(ctx);
  assert.equal(afterWake.hosts.get('123456789').mode,'persistent');
  await afterWake.webSocketMessage(host,JSON.stringify({type:'approve',token,accept:true}));
  assert.equal(viewer.last().type,'accepted');
  assert.equal(viewer.last().name,'Windows bilgisayar');
});
