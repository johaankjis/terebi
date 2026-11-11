import {startDisplay} from '/display/display.js';
import {installSessions, NAMESPACE} from './session.js';

const status = document.getElementById('status');
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
