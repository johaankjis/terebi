import {startDisplay, startMusic} from '/display/display.js';
import {installSessions, NAMESPACE} from './session.js';

const status = document.getElementById('status');
startMusic(); // the TV version starts its background music as soon as it opens
try {
  const context = cast.framework.CastReceiverContext.getInstance();
  installSessions(context, startDisplay, {ended: () => context.stop()});
  document.getElementById('fullscreen').hidden = true;
  context.start({
    customNamespaces: {[NAMESPACE]: cast.framework.system.MessageType.JSON},
    disableIdleTimeout: true, // documented for non-media receivers; stay after sender disconnect
    skipPlayersLoad: true,
  });
  status.textContent = 'Waiting for Hermes to connect this game';
} catch {
  status.textContent = 'Receiver could not start. Use the manual display link from Telegram.';
}
