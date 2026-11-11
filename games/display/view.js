// Pure presentation rules for the TV. No DOM: the same view drives 3D and static rendering.
// The server owns phases, timing and scores; this only decides what a snapshot looks like.

// The phone reads the gesture until +900 ms after Shoot, then posts it. Allow for that
// round trip and one display poll before telling the player to retry.
export const RETRY_AFTER_MS = 2000;

const NAMES = {rock: 'Rock', paper: 'Paper', scissors: 'Scissors'};
const OUTCOMES = {player: 'You win!', hermes: 'Hermes wins!', tie: 'It’s a tie!'};

const blank = {
  center: 'vs', count: '', moves: null, outcome: null,
  score: {player: 0, hermes: 0}, meta: '',
};

export function bootView(sub) {
  return {...blank, scene: 'boot', center: 'phone', headline: 'Welcome!', sub};
}

export function endedView(sub, last) {
  return {...blank, scene: 'ended', center: 'none', headline: 'Session ended', sub,
    score: last ? last.score : blank.score};
}

export function explain(result) {
  const {player_move: player, hermes_move: hermes, outcome} = result;
  if (outcome === 'tie') return `Both chose ${player}`;
  const [winner, loser] = outcome === 'player' ? [player, hermes] : [hermes, player];
  return `${NAMES[winner]} ${winner === 'scissors' ? 'beat' : 'beats'} ${loser}`;
}

// beat: seconds left on the countdown as already shown (3, 2, 1) or 0 once Shoot is up.
export function countdownBeat(state, now) {
  return Math.max(0, Math.min(3, Math.ceil((state.countdown_ends_at_ms - now) / 1000)));
}

export function present(state, now, {celebrating = false, beat = null} = {}) {
  const score = {player: state.score.player, hermes: state.score.hermes};
  const round = state.round_number ? `Round ${state.round_number} · ` : '';
  const view = {...blank, score, meta: `${round}Ties ${state.score.ties}`};
  const result = state.result && NAMES[state.result.player_move] && NAMES[state.result.hermes_move] &&
    OUTCOMES[state.result.outcome] ? state.result : null;

  switch (state.phase) {
    case 'waiting_for_player':
      return {...view, scene: 'waiting', center: 'phone', meta: '',
        headline: 'Waiting for you', sub: 'Open the pairing link on your phone.'};
    case 'ready':
      return celebrating
        ? {...view, scene: 'connected', center: 'check', headline: 'Phone connected', sub: 'Your phone is the controller.'}
        : {...view, scene: 'ready', headline: 'Ready', sub: 'Start the round on your phone.'};
    case 'countdown': {
      const left = beat === null ? countdownBeat(state, now) : beat;
      if (left > 0) {
        return {...view, scene: 'countdown', center: 'count', count: String(left),
          headline: 'Get ready', sub: 'Show your hand on Shoot.'};
      }
      if (now < state.countdown_ends_at_ms + RETRY_AFTER_MS) {
        return {...view, scene: 'shoot', center: 'count', count: 'Shoot!',
          headline: 'Show your hand', sub: 'Hold your gesture steady.'};
      }
      return {...view, scene: 'retry', center: 'retry',
        headline: 'Try again', sub: 'Tap Retry on your phone.'};
    }
    case 'reveal':
    case 'score':
    case 'next_round': {
      if (!result) return {...view, scene: 'ready', headline: 'Ready', sub: 'Start the round on your phone.'};
      return {...view,
        scene: state.phase === 'next_round' ? 'next' : state.phase,
        center: result.outcome === 'tie' ? 'tie' : 'vs',
        outcome: result.outcome,
        moves: {
          key: `${result.round_id}|${result.player_move}|${result.hermes_move}`,
          player: result.player_move, hermes: result.hermes_move,
          playerLabel: NAMES[result.player_move], hermesLabel: NAMES[result.hermes_move],
        },
        headline: OUTCOMES[result.outcome],
        sub: state.phase === 'next_round' ? 'Tap Next round on your phone.' : explain(result),
        meta: `${view.meta} · ${result.input === 'tap' ? 'Tap round' : 'Camera round'}`,
      };
    }
    default:
      return {...view, scene: 'ready', headline: 'Waiting', sub: ''};
  }
}
