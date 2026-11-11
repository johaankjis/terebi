import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const receiverSource = await readFile(new URL('../games/receiver/session.js', import.meta.url), 'utf8');
const {installSessions,NAMESPACE} = await import('data:text/javascript;base64,'+Buffer.from(receiverSource).toString('base64'));
const ID='session-id-123456789', TOKEN='viewer-token-123456789', REQUEST='challenge-id-123456789';
const message=(over={})=>({senderId:'sender-1',data:{type:'SHOW_SESSION',session_id:ID,display_token:TOKEN,request_id:REQUEST,...over}});
const state=(over={})=>({session_id:ID,revision:1,phase:'waiting_for_player',score:{player:0,hermes:0,ties:0,rounds:0},round_number:0,server_time_ms:1000,expires_at_ms:61000,...over});

function setup() {
  const sent=[], renders=[], paint=[]; let receive, stopped=0;
  const context={addCustomMessageListener(namespace,fn){assert.equal(namespace,NAMESPACE);receive=fn;},sendCustomMessage(...args){sent.push(args);}};
  const clear=installSessions(context,(credential,opts)=>{renders.push({credential,opts});return ()=>stopped++;},{afterPaint:fn=>paint.push(fn)});
  return {sent,renders,paint,clear,receive:ev=>receive(ev),get stopped(){return stopped;}};
}

test('receiver waits for session render and paint, then acknowledges only public identity',()=>{
  const h=setup();h.receive(message());
  assert.deepEqual(h.renders[0].credential,{id:ID,token:TOKEN});
  assert.equal(h.sent.length,0);
  h.renders[0].opts.onRendered(state());assert.equal(h.sent.length,0);
  h.paint.shift()();
  assert.deepEqual(h.sent[0],[NAMESPACE,'sender-1',{type:'DISPLAY_RENDERED',request_id:REQUEST,session_id:ID,phase:'waiting_for_player',revision:1}]);
  assert.ok(!JSON.stringify(h.sent).includes(TOKEN));
  h.renders[0].opts.onRendered(state({phase:'ready',revision:2}));h.paint.shift()();
  assert.equal(h.sent[1][2].phase,'ready');h.clear();
});

test('receiver ignores player/admin/URL payloads and wrong sessions',()=>{
  const h=setup();
  for(const data of [{admin_token:'secret'},{pairing_url:'forbidden'}, {session_id:'short'}, {display_token:'bad token'}]) h.receive(message(data));
  assert.equal(h.renders.length,0);
  h.receive(message());h.renders[0].opts.onRendered(state({session_id:'different-session-1234'}));
  assert.equal(h.paint.length,0);assert.equal(h.sent.length,0);h.clear();
});

test('switching sessions stops old renderer and ignores pending old render acknowledgements',()=>{
  const h=setup();h.receive(message());h.renders[0].opts.onRendered(state());
  h.receive(message({session_id:'second-session-123456'}));
  h.paint.shift()();
  assert.equal(h.stopped,1);assert.equal(h.sent.length,0);
  h.renders[0].opts.onRendered(state({revision:2}));
  assert.equal(h.paint.length,0);h.clear();
});

test('an older revision painted after a newer render is never acknowledged',()=>{
  const h=setup();h.receive(message());
  h.renders[0].opts.onRendered(state());h.renders[0].opts.onRendered(state({phase:'ready',revision:2}));
  h.paint.shift()();assert.equal(h.sent.length,0);
  h.paint.shift()();assert.equal(h.sent[0][2].revision,2);h.clear();
});

test('display failure does not become a render acknowledgement',()=>{
  const h=setup();h.receive(message());h.renders[0].opts.onFailure('display_unavailable');
  assert.equal(h.sent[0][2].type,'DISPLAY_FAILED');h.clear();
});

const displaySource=await readFile(new URL('../games/display/display.js',import.meta.url),'utf8');
test('shared display renders Waiting then Ready from matching session snapshots',async()=>{
  const nodes=new Map(), snapshots=[state(),state({phase:'ready',revision:2})], polls=[];
  const rendered=[];
  const context=vm.createContext({
    URLSearchParams,AbortController,performance,
    location:{pathname:'/receiver/'},
    document:{body:{dataset:{}},getElementById(id){if(!nodes.has(id))nodes.set(id,{textContent:''});return nodes.get(id);}},
    window:{addEventListener(){},removeEventListener(){}},
    setInterval(){return 1;},clearInterval(){},setTimeout(fn,delay){if(delay===400)polls.push(fn);return 1;},clearTimeout(){},
    fetch:async(path,opts)=>{assert.equal(path,'/v1/sessions/'+ID);assert.equal(opts.headers.Authorization,'Bearer '+TOKEN);return {ok:true,json:async()=>({ok:true,state:snapshots.shift()})};},
  });
  vm.runInContext(displaySource.replace('export function','function')+';globalThis.display=startDisplay;',context);
  const stop=context.display({id:ID,token:TOKEN},{onRendered:s=>rendered.push(s)});
  await new Promise(r=>setImmediate(r));
  assert.equal(nodes.get('headline').textContent,'Waiting for you');
  assert.equal(nodes.get('status').textContent,'Live · Waiting for a phone to pair');
  await polls.shift()();
  assert.equal(nodes.get('headline').textContent,'Ready');assert.equal(rendered.length,2);
  stop();
});

test('wrong or expired state cannot produce a rendered acknowledgement',async()=>{
  for(const snapshot of [state({session_id:'wrong-session-123456'}),state({expires_at_ms:1000})]) {
    const nodes=new Map(), rendered=[], failures=[];
    const context=vm.createContext({URLSearchParams,AbortController,performance,
      location:{pathname:'/receiver/'},
      document:{body:{dataset:{}},getElementById(id){if(!nodes.has(id))nodes.set(id,{textContent:''});return nodes.get(id);}},
      window:{addEventListener(){},removeEventListener(){}},
      setInterval(){return 1;},clearInterval(){},setTimeout(){return 1;},clearTimeout(){},
      fetch:async()=>({ok:true,json:async()=>({ok:true,state:snapshot})}),
    });
    vm.runInContext(displaySource.replace('export function','function')+';globalThis.display=startDisplay;',context);
    const stop=context.display({id:ID,token:TOKEN},{onRendered:s=>rendered.push(s),onFailure:r=>failures.push(r)});
    await new Promise(r=>setImmediate(r));
    assert.equal(rendered.length,0);assert.equal(failures.length,1);
    if(snapshot.expires_at_ms===1000)assert.equal(nodes.get('status').textContent,'Session ended');
    stop();
  }
});
