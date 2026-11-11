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

// The display script runs in a bare VM with its pure view rules inlined and a recording scene.
const strip=text=>text.replace(/^import .*$/gm,'').replace(/^export /gm,'');
const displaySource=strip(await readFile(new URL('../games/display/view.js',import.meta.url),'utf8'))+
  strip(await readFile(new URL('../games/display/display.js',import.meta.url),'utf8'))+
  ';globalThis.display=startDisplay;globalThis.tvMusic=startMusic;';
function tv({snapshots,Audio,status=200}={}) {
  const h={views:[],labels:[],celebrations:0,polls:[],rendered:[],failures:[],clock:0,tick:null};
  h.scene={render(view,opts={}){h.views.push({...view,instant:Boolean(opts.instant)});},
    connection(kind,label){h.labels.push([kind,label]);},celebrate(){h.celebrations++;},setMotion(){}};
  const context=vm.createContext({URLSearchParams,AbortController,Audio,performance:{now:()=>h.clock},
    location:{pathname:'/receiver/'},window:{addEventListener(){},removeEventListener(){}},
    setInterval(fn){h.tick=fn;return 1;},clearInterval(){},setTimeout(fn,delay){if(delay===400)h.polls.push(fn);return 1;},clearTimeout(){},
    fetch:async(path,opts)=>{assert.equal(path,'/v1/sessions/'+ID);assert.equal(opts.headers.Authorization,'Bearer '+TOKEN);
      return {ok:status===200,status,json:async()=>({ok:status===200,state:snapshots.length>1?snapshots.shift():snapshots[0]})};},
  });
  vm.runInContext(displaySource,context);
  h.context=context;
  h.start=()=>context.display({id:ID,token:TOKEN},{scene:h.scene,onRendered:s=>h.rendered.push(s),onFailure:r=>h.failures.push(r)});
  h.last=()=>h.views[h.views.length-1];
  h.settle=()=>new Promise(r=>setImmediate(r));
  return h;
}
const paired=(over={})=>state({phase:'ready',revision:2,round_id:'round-1',round_number:1,...over});

test('TV shows Waiting, plays the pairing transition once, then settles on Ready',async()=>{
  const h=tv({snapshots:[state(),paired(),paired()]});
  const stop=h.start();await h.settle();
  assert.equal(h.views[0].scene,'boot');
  assert.deepEqual([h.last().scene,h.last().headline,h.last().sub,h.last().center,h.last().instant],
    ['waiting','Waiting for you','Open the pairing link on your phone.','phone',true]);
  assert.deepEqual(h.labels[h.labels.length-1],['live','Live · Waiting for a phone to pair']);
  await h.polls.shift()();
  assert.equal(h.celebrations,1);
  assert.deepEqual([h.last().scene,h.last().headline,h.last().center,h.last().instant],['connected','Phone connected','check',false]);
  assert.deepEqual(h.labels[h.labels.length-1],['live','Live · Phone paired']);
  await h.polls.shift()();h.clock=2700;h.tick();
  assert.deepEqual([h.last().scene,h.last().headline,h.last().sub],['ready','Ready','Start the round on your phone.']);
  assert.equal(h.celebrations,1);assert.equal(h.rendered.length,3);
  stop();
});

test('reconnecting to an already paired session renders its state at once, with no transition',async()=>{
  const h=tv({snapshots:[paired({score:{player:2,hermes:1,ties:0,rounds:3}})]});
  const stop=h.start();await h.settle();
  assert.deepEqual([h.last().scene,h.last().headline,h.last().instant],['ready','Ready',true]);
  assert.equal(JSON.stringify(h.last().score),'{"player":2,"hermes":1}');
  assert.equal(h.celebrations,0);
  stop();
});

test('countdown beats never repeat when a poll re-anchors the clock',async()=>{
  const counting=over=>paired({phase:'countdown',revision:3,countdown_ends_at_ms:4000,accept_until_ms:14000,...over});
  const h=tv({snapshots:[counting({server_time_ms:2050}),counting({server_time_ms:1950}),counting({server_time_ms:4100}),counting({server_time_ms:6100})]});
  const stop=h.start();await h.settle();
  assert.deepEqual([h.last().scene,h.last().count],['countdown','2']);
  await h.polls.shift()();
  assert.equal(h.last().count,'2'); // an earlier server time must not bring 3 back
  await h.polls.shift()();
  assert.deepEqual([h.last().scene,h.last().count,h.last().moves],['shoot','Shoot!',null]);
  await h.polls.shift()();
  assert.deepEqual([h.last().scene,h.last().headline,h.last().sub],['retry','Try again','Tap Retry on your phone.']);
  stop();
});

test('connection label follows real polls: reconnecting on failure, live again on success',async()=>{
  const h=tv({snapshots:[state()]});
  const real=h.context.fetch;let fail=false;
  h.context.fetch=(...args)=>fail?Promise.reject(Error('offline')):real(...args);
  h.context.setTimeout=(fn)=>{h.polls.push(fn);return 1;};
  const stop=h.start();
  assert.deepEqual(h.labels[0],['connecting','Connecting to the game service…']);
  await h.settle();
  assert.equal(h.labels[h.labels.length-1][0],'live');
  fail=true;await h.polls.pop()();
  assert.deepEqual(h.labels[h.labels.length-1],['retrying','Reconnecting to the game service…']);
  assert.deepEqual(h.failures,['display_unavailable']);
  fail=false;await h.polls.pop()();
  assert.equal(h.labels[h.labels.length-1][0],'live');
  stop();
});

test('wrong or expired state cannot produce a rendered acknowledgement',async()=>{
  for(const snapshot of [state({session_id:'wrong-session-123456'}),state({expires_at_ms:1000})]) {
    const h=tv({snapshots:[snapshot]});
    const stop=h.start();await h.settle();
    assert.equal(h.rendered.length,0);assert.equal(h.failures.length,1);
    if(snapshot.expires_at_ms===1000){assert.equal(h.last().headline,'Session ended');assert.deepEqual(h.labels[h.labels.length-1],['ended','Session ended']);}
    stop();
  }
});

test('TV background music loops from one shared player and pauses when the display stops',()=>{
  const players=[];
  class Audio{constructor(src){this.src=src;players.push(this);this.loop=false;this.volume=1;this.played=0;this.paused=false;}
    play(){this.played++;return Promise.resolve();}pause(){this.paused=true;}}
  const h=tv({snapshots:[state()],Audio});
  const player=h.context.tvMusic();
  assert.deepEqual(players.map(p=>p.src),['/display/hydrate.mp3']);
  assert.ok(player.loop && player.volume===0.5 && player.played===1);
  const stop=h.start();
  assert.equal(players.length,1);assert.equal(player.played,2); // reuses the same looping player
  h.tick();assert.ok(!player.paused); // phase renders never interrupt the track
  stop();
  assert.ok(player.paused); // session over: music stops with the display
});

const {present,explain,RETRY_AFTER_MS}=await import('../games/display/view.js');
const result=(player_move,hermes_move,outcome,input='camera')=>({round_id:'round-1',player_move,hermes_move,outcome,input,nonce:'n'});
test('moves stay concealed until the server resolves the round, then both appear with the outcome',()=>{
  const base={...paired(),countdown_ends_at_ms:4000,accept_until_ms:14000};
  for(const [now,scene] of [[1500,'countdown'],[4000,'shoot'],[4000+RETRY_AFTER_MS,'retry']]) {
    const view=present({...base,phase:'countdown'},now);
    assert.equal(view.scene,scene);assert.equal(view.moves,null);assert.equal(view.outcome,null);
  }
  const won={...base,phase:'reveal',result:result('rock','scissors','player'),score:{player:1,hermes:0,ties:0,rounds:1}};
  const view=present(won,5000);
  assert.deepEqual([view.scene,view.headline,view.sub,view.outcome],['reveal','You win!','Rock beats scissors','player']);
  assert.deepEqual([view.moves.player,view.moves.hermes,view.moves.playerLabel,view.moves.hermesLabel],['rock','scissors','Rock','Scissors']);
  assert.deepEqual(view.score,{player:1,hermes:0});
  assert.equal(present({...won,phase:'score'},6000).moves.key,view.moves.key); // one reveal per round
  const next=present({...won,phase:'next_round'},8000);
  assert.deepEqual([next.scene,next.headline,next.sub],['next','You win!','Tap Next round on your phone.']);
});

test('wins, losses and ties read differently in words, not only in color',()=>{
  assert.equal(explain(result('paper','scissors','hermes')),'Scissors beat paper');
  assert.equal(explain(result('paper','rock','player')),'Paper beats rock');
  const lost=present({...paired(),phase:'reveal',result:result('paper','scissors','hermes','tap')},0);
  assert.deepEqual([lost.headline,lost.outcome,lost.center],['Hermes wins!','hermes','vs']);
  assert.match(lost.meta,/Tap round$/);
  const tie=present({...paired(),phase:'reveal',result:result('rock','rock','tie')},0);
  assert.deepEqual([tie.headline,tie.sub,tie.outcome,tie.center],['It’s a tie!','Both chose rock','tie','tie']);
  assert.match(tie.meta,/Camera round$/);
});

const {handPrims,handFrame,createHands}=await import('../games/display/hands.js');
test('each move has its own hand rig, and Hermes mirrors the player',()=>{
  const shapes=['rock','paper','scissors'].map(move=>JSON.stringify(handPrims(move)));
  assert.equal(new Set(shapes).size,3);assert.equal(handPrims('lizard'),null);
  for(const move of ['rock','paper','scissors']) {
    const left=handFrame(move,false,1), right=handFrame(move,true,1);
    assert.ok(left.length>20);
    for(const [i,p] of left.entries()) {
      for(const v of [...p.L,...p.T]) assert.ok(Number.isFinite(v)&&Math.abs(v)<=1);
      assert.ok(Math.abs(p.T[0]+right[i].T[0])<1e-9&&Math.abs(p.T[1]-right[i].T[1])<1e-9);
    }
  }
});

test('both hands reveal on the same frame; without WebGL the static painter draws the same moves',()=>{
  const drawn=[], frames=[]; let now=0;
  const canvas=name=>({name,width:2,height:2,clientWidth:300,parentNode:null,addEventListener(){},cloneNode(){return canvas(name);},
    getContext(kind){if(kind!=='2d')return null;const record=()=>{};
      return {setTransform:record,clearRect(){drawn.push([name,frames.length]);},beginPath:record,ellipse:record,fill:record,moveTo:record,lineTo:record,stroke:record};}});
  globalThis.window={devicePixelRatio:1};
  const hands=createHands([{canvas:canvas('player'),mirrored:false},{canvas:canvas('hermes'),mirrored:true}],
    {raf:fn=>{frames.push(fn);return frames.length;},caf(){},clock:()=>now});
  assert.equal(hands.is3d(),false);
  hands.show(['rock','scissors'],true);
  assert.deepEqual(drawn,[['player',0],['hermes',0]]); // first frame paints both
  now=400;frames[0]();
  assert.deepEqual(drawn.slice(2),[['player',1],['hermes',1]]);
  now=900;frames[1]();assert.equal(frames.length,2); // settled: the loop ends
  drawn.length=0;hands.show(['paper','paper'],false);
  assert.deepEqual(drawn.map(d=>d[0]),['player','hermes']);assert.equal(frames.length,2); // still mode: one paint, no loop
  delete globalThis.window;
});
