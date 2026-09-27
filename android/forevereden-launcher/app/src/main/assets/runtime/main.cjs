'use strict';
const fs = require('node:fs');
const path = require('node:path');
const mode = process.argv[2], root = path.resolve(process.argv[3]);
if (!['capture','private'].includes(mode) || !path.isAbsolute(root)) throw new Error('Usage: main.cjs capture|private ABSOLUTE_APP_ROOT [PROFILE]');
const runtime = __dirname, codec = JSON.parse(fs.readFileSync(path.join(runtime, 'codec.json')));
const log = line => fs.appendFileSync(path.join(root, 'server.log'), `${line}\n`, { encoding: 'utf8', mode: 0o600 });
let app, port;
if (mode === 'capture') {
  const { createCaptureProxy } = require('./forevereden_capture_proxy.cjs');
  app = createCaptureProxy({ codec, outputDir: path.join(root, 'profiles'), tls: {
    key: fs.readFileSync(path.join(runtime, 'capture-key.pem')),
    cert: fs.readFileSync(path.join(runtime, 'capture-cert.pem')),
  }, log });
  port = 28764;
} else {
  const { createMobileServer, loadResourceDirectory } = require('./forevereden_mobile_server.cjs');
  const requested = process.argv[4] ? path.resolve(process.argv[4]) : null;
  const profileRoot = path.join(root, 'profiles');
  if (requested && path.dirname(requested) !== profileRoot) throw new Error('Profile escapes the user manager');
  const seedFile = requested && fs.existsSync(requested) ? requested : path.join(runtime, 'seed.json');
  app = createMobileServer({
    seed: JSON.parse(fs.readFileSync(seedFile)), codec,
    statePath: path.join(root, `private-state-${path.basename(seedFile, '.json')}.json`),
    resources: loadResourceDirectory(path.join(runtime, 'resources'), 'ec741d3cc2f29b867892b1ed16a7a59b40e3968d'), log,
  });
  port = 28765;
}
app.server.listen(port, '127.0.0.1', 8, () => {
  const status = { version: 1, mode, port, pid: process.pid, ready: true, started_at: new Date().toISOString() };
  const target = path.join(root, 'listener-status.json'), temporary = `${target}.tmp-${process.pid}`;
  fs.writeFileSync(temporary, `${JSON.stringify(status)}\n`, { mode: 0o600 }); fs.renameSync(temporary, target);
  console.log(JSON.stringify(status));
});
