'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { ACTIONS, createMobileServer, loadResourceDirectory } = require('./forevereden_mobile_server.cjs');

const root = path.resolve(__dirname, '..'), port = 28765;
const mumuAdb = path.join(process.env.ProgramFiles || 'C:\\Program Files', 'Netease', 'MuMuPlayerARM', 'shell', 'adb.exe');
const adb = process.env.ADB || (process.platform === 'win32' && fs.existsSync(mumuAdb) ? mumuAdb : 'adb');
const launcher = 'dev.forevereden.launcher', service = `${launcher}/.NodeListenerService`;
const game = 'games.fed.anothereden/net.wrightflyer.toybox.AppActivity';
const run = (args, timeout = 15000) => execFileSync(adb, args,
  { encoding: 'utf8', timeout, maxBuffer: 20 * 1024 * 1024, windowsHide: true }).trim();
function serial() {
  if (process.env.ANDROID_SERIAL) return process.env.ANDROID_SERIAL;
  const stateFile = path.join(process.env.ProgramFiles || 'C:\\Program Files',
    'Netease', 'MuMuPlayerARM', 'vms', 'vm2.gmadoa', 'misc', 'state.json');
  if (process.platform === 'win32' && fs.existsSync(stateFile)) {
    const state = JSON.parse(fs.readFileSync(stateFile, 'utf8').replace(/^\uFEFF/, ''));
    if (/^10\.0\.2\.\d{1,3}$/.test(state.AdbHost) && Number.isInteger(state.AdbPort)) {
      const value = `${state.AdbHost}:${state.AdbPort}`;
      try { run(['connect', value], 5000); if (run(['-s', value, 'get-state'], 5000) === 'device') return value; } catch {}
      throw new Error(`Start the ForeverEden MuMu instance (${value} is offline)`);
    }
  }
  const devices = run(['devices']).split(/\r?\n/).map(line => /^(\S+)\s+device(?:\s|$)/.exec(line))
    .filter(Boolean).map(match => match[1]);
  if (devices.length !== 1) throw new Error('Start ForeverEden first; with multiple devices, set ANDROID_SERIAL');
  return devices[0];
}
const readJson = file => JSON.parse(fs.readFileSync(file));
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object'
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
let listenerApp;

(async () => {
  const device = serial(), call = args => run(['-s', device, ...args]);
  if (!call(['shell', 'pm', 'list', 'packages', launcher]).split(/\r?\n/).includes(`package:${launcher}`) ||
      !call(['shell', 'pm', 'list', 'packages', 'games.fed.anothereden']).split(/\r?\n/).includes('package:games.fed.anothereden'))
    throw new Error('Install the ForeverEden launcher and private client first');
  const preferences = call(['exec-out', 'run-as', launcher, 'cat', 'shared_prefs/MainActivity.xml']);
  const selected = /<string name="active_profile">(forevereden-profile-[0-9a-f]{16}\.json)<\/string>/.exec(preferences)?.[1] ?? '';
  const manifest = readJson(path.join(root, 'forevereden/local-runtime-identity.json')), identity = manifest.identity;
  if (manifest.runtime_id !== hash(JSON.stringify(canonical(identity)))) throw new Error('Invalid local runtime identity');
  for (const [file, digest] of Object.entries(identity.active_server ?? {}))
    if (hash(fs.readFileSync(path.join(root, file))) !== digest) throw new Error(`Active server changed: ${file}`);
  if (!Array.isArray(identity.routed_routes) || identity.routed_routes.length !== ACTIONS.size ||
      identity.routed_routes.some(action => !ACTIONS.has(action))) throw new Error('Active route inventory mismatch');
  const probe = readJson(path.join(root, 'forevereden/private-probe-identity.json'));
  if (probe.runtime_id !== identity.private_client_runtime_id || probe.runtime_id !== hash(JSON.stringify(canonical(probe.identity))))
    throw new Error('Private client generation mismatch');
  const seed = selected
    ? JSON.parse(call(['exec-out', 'run-as', launcher, 'cat', `files/forevereden/profiles/${selected}`]))
    : readJson(path.join(root, identity.seed.path));
  const stateName = `private-state-${selected ? path.basename(selected, '.json') : 'seed'}.json`;
  let initialState;
  try { initialState = JSON.parse(call(['exec-out', 'run-as', launcher, 'cat', `files/forevereden/${stateName}`])); } catch {}
  const database = path.join(root, 'data/forevereden-evidence/private-login',
    `mobile-${selected ? path.basename(selected, '.json') : 'starter'}.sqlite`);
  const app = listenerApp = createMobileServer({ seed, codec: readJson(path.join(root, identity.codec.path)), database, initialState,
    resources: loadResourceDirectory(path.join(root, 'data/forevereden-evidence/private-resources'), identity.content_generation) });
  await new Promise((resolve, reject) => app.server.once('error', reject).listen(port, '127.0.0.1', 8, resolve));
  try { call(['shell', 'run-as', launcher, 'am', 'start-service', '--user', '0', '-n', service, '-a', `${launcher}.listener.STOP`]); } catch {}
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 500);
  try { call(['reverse', '--remove', `tcp:${port}`]); } catch {}
  call(['reverse', `tcp:${port}`, `tcp:${port}`]);
  call(['shell', 'am', 'start', '-n', game]);
  console.log(`ForeverEden listener: ${device} loopback -> host SQLite (${selected || 'bundled profile'})`);
  console.log(`Profile database: ${database}`);
  console.log('The private client is connected. Press Ctrl+C to stop the listener.');
  let stopping = false, misses = 0;
  const monitor = setInterval(() => {
    try {
      if (!call(['reverse', '--list']).split(/\r?\n/).some(line => line.includes(`tcp:${port} tcp:${port}`))) throw new Error();
      misses = 0;
    } catch {
      if (++misses >= 3) stop(1, new Error('ADB reverse exited'));
    }
  }, 5000);
  async function stop(code, error) {
    if (stopping) return; stopping = true; clearInterval(monitor);
    if (error) console.error(error.message);
    try { call(['reverse', '--remove', `tcp:${port}`]); } catch {}
    await app.close(); process.exitCode = code;
  }
  process.on('SIGINT', () => stop(0)); process.on('SIGTERM', () => stop(0));
})().catch(async error => {
  console.error(error.message);
  if (listenerApp?.server.listening) await listenerApp.close();
  process.exitCode = 1;
});
