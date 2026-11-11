import {startDisplay, startMusic} from '/display/display.js';
import {getScene} from '/display/scene.js';
import {bootView} from '/display/view.js';
import {installSessions, NAMESPACE} from './session.js';

const scene = getScene();
scene.hideFullscreen();
scene.render(bootView('Waiting for Hermes to connect this game.'), {instant: true});
startMusic(); // the TV version starts its background music as soon as it opens
try {
  const context = cast.framework.CastReceiverContext.getInstance();
  installSessions(context, startDisplay, {ended: () => context.stop()});
  context.start({
    customNamespaces: {[NAMESPACE]: cast.framework.system.MessageType.JSON},
    disableIdleTimeout: true, // documented for non-media receivers; stay after sender disconnect
    skipPlayersLoad: true,
  });
  scene.connection('connecting', 'Waiting for Hermes to connect this game');
} catch {
  scene.connection('retrying', 'Receiver could not start. Use the manual display link from Telegram.');
}
