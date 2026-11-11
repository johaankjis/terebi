import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';

const receiverSource = await readFile(new URL('../games/receiver/session.js', import.meta.url), 'utf8');
const {installSessions,NAMESPACE,confirmEnded} = await import('data:text/javascript;base64,'+Buffer.from(receiverSource).toString('base64'));
const ID='session-id-123456789', TOKEN='viewer-token-123456789', REQUEST='challenge-id-123456789';
const message=(over={})=>({senderId:'sender-1',data:{type:'SHOW_SESSION',session_id:ID,display_token:TOKEN,request_id:REQUEST,...over}});
const state=(over={})=>({session_id:ID,revision:1,phase:'waiting_for_player',score:{player:0,hermes:0,ties:0,rounds:0},round_number:0,server_time_ms:1000,expires_at_ms:61000,...over});

function setup({verifyEnded=async()=>false}={}) {
  const sent=[], renders=[], paint=[]; let receive, stopped=0, ended=0;
  const context={addCustomMessageListener(namespace,fn){assert.equal(namespace,NAMESPACE);receive=fn;},sendCustomMessage(...args){sent.push(args);}};
  const clear=installSessions(context,(credential,opts)=>{renders.push({credential,opts});return ()=>stopped++;},{afterPaint:fn=>paint.push(fn),verifyEnded,ended:()=>ended++});
  return {sent,renders,paint,clear,receive:ev=>receive(ev),get stopped(){return stopped;},get ended(){return ended;}};
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
function tv({snapshots,Audio}={}) {
  const h={views:[],labels:[],celebrations:0,polls:[],timers:[],posts:[],rendered:[],failures:[],clock:0,tick:null,offline:false};
  h.scene={render(view,opts={}){h.views.push({...view,instant:Boolean(opts.instant)});},
    connection(kind,label){h.labels.push([kind,label]);},celebrate(){h.celebrations++;},setMotion(){},
    profile:()=>({mode:'3d',tier:'full',turn:'gl',ambient:[180,17,21,0],screen:[1280,720,100]})};
  const context=vm.createContext({URLSearchParams,AbortController,Audio,performance:{now:()=>h.clock},
    location:{pathname:'/receiver/'},window:{addEventListener(){},removeEventListener(){}},
    setInterval(fn){h.tick=fn;return 1;},clearInterval(){},clearTimeout(){},
    setTimeout(fn,delay){(fn.name==='poll'?h.polls:h.timers).push({fn,delay});return 1;},
    fetch:async(path,opts)=>{
      if(h.offline)throw Error('offline');
      if(h.ended)return {ok:false,status:410,json:async()=>({ok:false,reason:'session_ended'})};
      assert.equal(opts.headers.Authorization,'Bearer '+TOKEN);
      if(opts.method==='POST'){h.posts.push({path,body:JSON.parse(opts.body)});return {ok:true,json:async()=>({ok:true})};}
      assert.equal(path,'/v1/sessions/'+ID);
      return {ok:true,status:200,json:async()=>({ok:true,state:snapshots.length>1?snapshots.shift():snapshots[0]})};},
  });
  vm.runInContext(displaySource,context);
  h.context=context;
  h.start=()=>context.display({id:ID,token:TOKEN},{scene:h.scene,onRendered:s=>h.rendered.push(s),onFailure:r=>h.failures.push(r)});
  h.last=()=>h.views[h.views.length-1];
  h.poll=()=>h.polls.shift().fn();
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
  await h.poll();
  assert.equal(h.celebrations,1);
  assert.deepEqual([h.last().scene,h.last().headline,h.last().center,h.last().instant],['connected','Phone connected','check',false]);
  assert.deepEqual(h.labels[h.labels.length-1],['live','Live · Phone paired']);
  // The hand-off to Ready is scheduled for the moment the transition ends, not left to a tick.
  const settle=h.timers.find(t=>t.fn.name==='render'&&t.delay>2000);
  assert.ok(settle);
  await h.poll();h.clock=settle.delay;settle.fn();
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

test('countdown beats are timed locally, one second apart, and a late poll cannot move them',async()=>{
  const counting=over=>paired({phase:'countdown',revision:3,countdown_ends_at_ms:4000,accept_until_ms:14000,...over});
  // The second poll claims an earlier server time and the third a later one: neither may shift a beat.
  const h=tv({snapshots:[counting({server_time_ms:1050}),counting({server_time_ms:700}),counting({server_time_ms:2600})]});
  const beatTimer=()=>h.timers.filter(t=>t.fn.name==='render').pop();
  const stop=h.start();await h.settle();
  assert.deepEqual([h.last().scene,h.last().center,h.last().count],['countdown','count','3']);
  assert.equal(beatTimer().delay,951); // 2950 ms left: the 2 lands in 950 ms, plus a 1 ms guard
  await h.poll();assert.equal(h.last().count,'3');
  h.clock=951;beatTimer().fn();assert.equal(h.last().count,'2');
  assert.equal(beatTimer().delay,1000);
  await h.poll();assert.equal(h.last().count,'2'); // a poll far ahead does not skip to 1
  h.clock=1951;beatTimer().fn();assert.equal(h.last().count,'1');
  h.clock=1900;h.tick();assert.equal(h.last().count,'1'); // a beat already shown never comes back
  h.clock=2951;beatTimer().fn();
  assert.deepEqual([h.last().scene,h.last().center,h.last().moves],['shoot','shoot',null]);
  assert.equal(beatTimer().delay,2000); // then the retry prompt, if no move arrives
  h.clock=4951;beatTimer().fn();
  assert.deepEqual([h.last().scene,h.last().headline,h.last().sub],['retry','Try again','Tap Retry on your phone.']);
  stop();
});

test('connection label follows real polls: reconnecting on failure, live again on success',async()=>{
  const h=tv({snapshots:[state()]});
  const stop=h.start();
  assert.deepEqual(h.labels[0],['connecting','Connecting to the game service…']);
  await h.settle();
  assert.equal(h.labels[h.labels.length-1][0],'live');
  h.offline=true;await h.poll();
  assert.deepEqual(h.labels[h.labels.length-1],['retrying','Reconnecting to the game service…']);
  assert.deepEqual(h.failures,['display_unavailable']);
  assert.equal(h.polls[0].delay,2000);
  h.offline=false;await h.poll();
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

test('the TV reports its own render timings with the display credential, numbers only',async()=>{
  const h=tv({snapshots:[state()]});
  const stop=h.start();await h.settle();
  const report=h.timers.find(t=>t.fn.name==='report');
  assert.ok(report.delay>=10000); // after the ambient scene has been measured
  report.fn();await h.settle();
  assert.equal(h.posts[0].path,'/v1/sessions/'+ID+'/profile');
  assert.deepEqual(Object.keys(h.posts[0].body).sort(),['ambient','mode','screen','tier','turn']);
  assert.ok(!JSON.stringify(h.posts).includes(TOKEN));
  h.offline=true;report.fn(); // a failed report is silent and never touches the game
  await h.settle();assert.deepEqual(h.failures,[]);
  stop();
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

const {handPrims,handFrame,handPose,createHands,decodeHands,TURN_MS}=await import('../games/display/hands.js');
const baked=JSON.parse(await readFile(new URL('../games/display/hands.json',import.meta.url),'utf8'));
const decode=text=>new Uint8Array(Buffer.from(text,'base64'));
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

test('the reveal turn starts from nothing, overshoots softly and ends exactly on the resting pose',()=>{
  const size=t=>Math.hypot(...handPose('rock',false,t).slice(0,3));
  const rest=size(1);
  assert.ok(size(0)<rest*0.01);
  let peak=0; for(let t=0;t<=1;t+=0.01) { peak=Math.max(peak,size(t)); assert.ok(size(t)<=rest*1.08); }
  assert.ok(peak>rest*1.03); // a visible but soft bounce
  assert.ok(Math.abs(size(0.999)-rest)<rest*0.002); // no pop at the end
  const near=handPose('scissors',true,0.999), end=handPose('scissors',true,1);
  for(let k=0;k<9;k++) assert.ok(Math.abs(near[k]-end[k])<0.01);
});

test('baked hand meshes decode for every move and reject damaged data',()=>{
  const meshes=decodeHands(baked,decode);
  for(const move of ['rock','paper','scissors']) {
    assert.ok(meshes[move].index.length>=9000&&meshes[move].position.length/3<20000); // smooth, still small
    assert.equal(meshes[move].normalShade.length/4,meshes[move].position.length/3);
  }
  assert.equal(decodeHands({...baked,version:2},decode),null);
  assert.equal(decodeHands({...baked,moves:{...baked.moves,paper:{...baked.moves.paper,vertices:3}}},decode),null);
  assert.equal(decodeHands(null,decode),null);
});

function fakeCanvas(name,log,{webgl=false}={}) {
  const classes=new Set();
  const gl=new Proxy({},{get:(_,key)=>key==='drawElements'?()=>log.push(name):
    key==='getShaderParameter'||key==='getProgramParameter'?()=>true:
    typeof key==='string'&&/^[A-Z_0-9]+$/.test(key)?1:()=>({})});
  const record=()=>{};
  return {name,width:2,height:2,clientWidth:300,offsetWidth:300,parentNode:null,addEventListener(){},
    classList:{add:c=>classes.add(c),remove:c=>classes.delete(c),contains:c=>classes.has(c)},
    cloneNode(){return fakeCanvas(name,log,{webgl});},
    getContext(kind){if(kind==='2d')return {setTransform:record,clearRect(){log.push(name);},beginPath:record,ellipse:record,fill:record,moveTo:record,lineTo:record,stroke:record};
      return webgl?gl:null;}};
}
function handsRig(webgl) {
  const h={log:[],frames:[],later:[],now:0,landed:0};
  globalThis.window={devicePixelRatio:1};
  h.hands=createHands([{canvas:fakeCanvas('player',h.log,{webgl}),mirrored:false},{canvas:fakeCanvas('hermes',h.log,{webgl}),mirrored:true}],
    {raf:fn=>{h.frames.push(fn);return h.frames.length;},caf(){},clock:()=>h.now,later:(fn,ms)=>h.later.push({fn,ms})});
  h.hands.setMeshes(webgl?decodeHands(baked,decode):null);
  while(h.frames.length)h.frames.pop()(); // the warm-up frame is shown, then cleared
  h.log.length=0;
  h.frame=ms=>{h.now+=ms;h.frames.pop()();};
  return h;
}

test('3D hands turn together frame by frame, and the outcome waits until they land',()=>{
  const h=handsRig(true);
  assert.ok(h.hands.is3d());assert.equal(h.hands.turnStyle(),'gl');
  h.hands.show(['rock','scissors'],true,()=>h.landed++);
  assert.deepEqual(h.log,['player','hermes']); // both painted before the first animated frame
  let frames=0;
  while(h.frames.length){h.log.length=0;h.frame(16);frames++;assert.deepEqual(h.log,['player','hermes']);
    if(frames*16<TURN_MS*0.8)assert.equal(h.landed,0);}
  assert.equal(h.landed,1);
  assert.ok(Math.abs(frames*16-TURN_MS)<=32); // a steady device finishes on time
  assert.equal(h.hands.turnStyle(),'gl');
  delete globalThis.window;
});

test('a stalled frame stretches the turn instead of skipping it; a slow device moves to the compositor',()=>{
  const h=handsRig(true);
  h.hands.show(['paper','rock'],true,()=>h.landed++);
  h.frame(16);h.frame(600); // one long hitch
  assert.equal(h.landed,0);assert.equal(h.frames.length,1); // still turning: 600 ms counted as 40
  let frames=2; while(h.frames.length){h.frame(60);frames++;} // then a device that manages ~16 fps
  assert.equal(h.landed,1);
  assert.ok(frames>20); // every step was drawn; none were jumped over
  assert.equal(h.hands.turnStyle(),'css'); // next reveal: paint once, let the compositor swing it
  h.log.length=0;h.hands.show(['rock','rock'],true,()=>h.landed++);
  assert.deepEqual(h.log,['player','hermes']);assert.equal(h.frames.length,0);
  assert.equal(h.later.length,1);h.later[0].fn();assert.equal(h.landed,2);
  delete globalThis.window;
});

test('a hidden rehearsal decides the turn style before the first real reveal',()=>{
  const steady=handsRig(true);
  steady.hands.rehearse();
  while(steady.frames.length)steady.frame(17);
  assert.equal(steady.hands.turnStyle(),'gl');assert.ok(steady.hands.lastTurn().frames>=10);
  const stalling=handsRig(true);
  stalling.hands.rehearse();
  stalling.frame(17);stalling.frame(900); // one stall while the scene is animating
  while(stalling.frames.length)stalling.frame(17);
  assert.equal(stalling.hands.turnStyle(),'css');
  const busy=handsRig(true); // a reveal that arrives mid-rehearsal wins: the rehearsal stops drawing
  busy.hands.rehearse();busy.frame(17);
  busy.hands.show(['rock','paper'],true,()=>busy.landed++);
  busy.log.length=0;busy.frames.shift()(); // the stale rehearsal frame
  assert.deepEqual(busy.log,[]);
  delete globalThis.window;
});

test('the canvases start drawing unseen before a reveal, and the turn takes over without a gap',()=>{
  const h=handsRig(true);
  h.hands.prime(true);
  h.frame(17);h.frame(17);
  assert.deepEqual(h.log,['player','hermes','player','hermes']); // invisible frames keep the pipeline warm
  h.hands.show(['paper','rock'],true,()=>h.landed++);
  h.log.length=0;h.frames.shift()(); // the stale priming frame does nothing
  assert.deepEqual(h.log,[]);
  while(h.frames.length)h.frame(16);
  assert.equal(h.landed,1);assert.equal(h.hands.turnStyle(),'gl');
  h.hands.clear();h.hands.prime(true);h.frame(17);h.hands.prime(false); // a retry: nothing stays on screen
  h.log.length=0;if(h.frames.length)h.frames.pop()();assert.deepEqual(h.log,[]);
  delete globalThis.window;
});

test('without WebGL the same moves are painted flat, both at once, with compositor motion',()=>{
  const h=handsRig(false);
  assert.equal(h.hands.is3d(),false);assert.equal(h.hands.turnStyle(),'css');
  h.hands.show(['rock','scissors'],true,()=>h.landed++);
  assert.deepEqual(h.log,['player','hermes']);assert.equal(h.frames.length,0);
  h.later[0].fn();assert.equal(h.landed,1);
  h.log.length=0;h.hands.show(['paper','paper'],false,()=>h.landed++); // still mode: one paint, landed at once
  assert.deepEqual(h.log,['player','hermes']);assert.equal(h.landed,2);
  delete globalThis.window;
});


test('only a matching server-ended session exits the receiver, once',async()=>{
  const h=setup({verifyEnded:async credentials=>{assert.deepEqual(credentials,{id:ID,token:TOKEN});return true;}});
  h.receive(message());
  await h.receive(message({type:'END_SESSION'}));
  assert.equal(h.stopped,1);assert.equal(h.ended,1);
  assert.equal(h.sent.at(-1)[2].type,'SESSION_ENDING');
  assert.ok(!JSON.stringify(h.sent).includes(TOKEN));
  await h.receive(message({type:'END_SESSION'}));
  assert.equal(h.ended,1);assert.equal(h.sent.at(-1)[2].type,'SESSION_UNKNOWN');h.clear();
});

test('read-only viewer cannot stop a live game or a newer receiver session',async()=>{
  const h=setup({verifyEnded:async()=>false});h.receive(message());
  await h.receive(message({type:'END_SESSION'}));
  assert.equal(h.stopped,0);assert.equal(h.ended,0);
  h.receive(message({session_id:'second-session-123456'}));
  await h.receive(message({type:'END_SESSION'}));
  assert.equal(h.stopped,1);assert.equal(h.ended,0);
  assert.equal(h.sent.at(-1)[2].type,'SESSION_NOT_CURRENT');h.clear();
});

test('new game arriving while end verification is pending survives the old stop',async()=>{
  let resolve;const pending=new Promise(r=>resolve=r);
  const h=setup({verifyEnded:()=>pending});h.receive(message());
  const stopping=h.receive(message({type:'END_SESSION'}));
  h.receive(message({session_id:'second-session-123456'}));
  resolve(true);await stopping;
  assert.equal(h.ended,0);assert.equal(h.stopped,1);h.clear();
});

test('receiver verifies revocation against its own origin and never sends a write token',async()=>{
  const original=globalThis.fetch;
  try{
    for(const [status,reason,expected] of [[200,'live',false],[401,'unauthorized',false],
      [410,'session_ended',true],[410,'session_expired',true],[404,'session_missing',true],[503,'failed',false]]){
      globalThis.fetch=async(path,opts)=>{
        assert.equal(path,'/v1/sessions/'+ID);
        assert.equal(opts.headers.Authorization,'Bearer '+TOKEN);
        assert.equal(opts.body,undefined);
        return {status,json:async()=>({ok:status===200,reason})};
      };
      assert.equal(await confirmEnded({id:ID,token:TOKEN}),expected);
    }
  }finally{globalThis.fetch=original;}
});

test('revoked display polling pauses the soundtrack and reports session ended',async()=>{
  let pauses=0;
  class Audio {play(){return Promise.resolve();}pause(){pauses++;}}
  const h=tv({snapshots:[state()],Audio});h.start();await h.settle();
  h.ended=true;await h.poll();
  assert.ok(pauses>=1);assert.equal(h.failures.at(-1),'session_ended');
  assert.equal(h.last().scene,'ended');
});
