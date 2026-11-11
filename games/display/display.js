const el = id => document.getElementById(id);
const fragment = new URLSearchParams(location.hash.slice(1));
let credentials;
try {
  if (fragment.has('session') && fragment.has('token')) {
    credentials = {id: fragment.get('session'), token: fragment.get('token')};
    sessionStorage.setItem('terebi-display', JSON.stringify(credentials));
  } else credentials = JSON.parse(sessionStorage.getItem('terebi-display'));
} catch { credentials = null; }
history.replaceState(null, '', location.pathname);
let state = null, anchored = 0, request = null, timer = null, stopped = false;
const labels = {rock:'✊ Rock', paper:'✋ Paper', scissors:'✌ Scissors'};
function render() {
  if (!state) return;
  const now = state.server_time_ms + performance.now() - anchored;
  if (now >= state.expires_at_ms) {stop(); el('headline').textContent='Session ended';el('status').textContent='Session ended';el('guidance').textContent='Ask Hermes for a new game.';return;}
  document.body.dataset.phase = state.phase;
  el('round').textContent = state.round_number ? `· ROUND ${state.round_number}` : '';
  const titles = {waiting_for_player:'Waiting for you',ready:'Ready',reveal:'Reveal!',score:'The score',next_round:'Play again?'};
  const hints = {waiting_for_player:'Open the pairing link on your phone.',ready:'Position your hand, then start on your phone.',reveal:'Moves are locked.',score:'One round. One result.',next_round:'Tap Next round on your phone.'};
  if (state.phase === 'countdown') {
    const left = Math.ceil((state.countdown_ends_at_ms-now)/1000);
    el('headline').textContent = left>0 ? String(Math.min(3,left)) : 'Shoot!';
    el('guidance').textContent = left>0 ? 'Rock, paper, scissors…' : 'Hold your gesture. Unclear? Retry on your phone.';
  } else {el('headline').textContent=titles[state.phase]||'Waiting';el('guidance').textContent=hints[state.phase]||'';}
  const show = ['reveal','score','next_round'].includes(state.phase) && state.result;
  el('moves').hidden=!show;
  el('result').textContent=show ? {player:'You win!',hermes:'Hermes wins!',tie:'It’s a tie!'}[state.result.outcome] : '';
  el('input').textContent=show ? (state.result.input==='tap'?'Tap-to-play fallback round':'Camera round') : '';
  if(show){el('player-move').textContent=labels[state.result.player_move];el('hermes-move').textContent=labels[state.result.hermes_move];}
  el('player-score').textContent=state.score.player;el('hermes-score').textContent=state.score.hermes;el('ties').textContent=state.score.ties;
  el('completed').textContent=`${state.score.rounds} rounds played`;
}
async function poll(){
  if(stopped||!credentials)return;
  request=new AbortController(); const timeout=setTimeout(()=>request?.abort(),4000);
  let delay=400;
  try{
    const r=await fetch(`/v1/sessions/${encodeURIComponent(credentials.id)}`,{headers:{Authorization:`Bearer ${credentials.token}`},cache:'no-store',signal:request.signal});
    const data=await r.json();
    if(!r.ok||!data.ok){if([401,404,410].includes(r.status)){stop();el('headline').textContent='Session ended';el('status').textContent='Session ended';el('guidance').textContent='Open a fresh display link from Hermes.';return;}throw Error('connection');}
    if(!state||data.state.revision>=state.revision){state=data.state;anchored=performance.now();render();}
    el('status').textContent=state.phase==='waiting_for_player'
      ? 'Live · Waiting for a phone to pair'
      : 'Live · Your paired phone controls the game';
  }catch{el('status').textContent='Connection interrupted — reconnecting…';delay=2000;}
  finally{clearTimeout(timeout);request=null;if(!stopped)timer=setTimeout(poll,delay);}
}
function stop(){stopped=true;clearTimeout(timer);request?.abort();}
el('fullscreen').addEventListener('click',async()=>{try{if(!document.fullscreenElement)await document.documentElement.requestFullscreen();else await document.exitFullscreen();}catch{el('status').textContent='Use Chrome’s fullscreen menu, then cast this tab.';}});
window.addEventListener('pagehide',stop);
setInterval(render,100);
if(credentials?.id&&credentials?.token)poll();
