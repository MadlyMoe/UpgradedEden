'use strict';
// Legacy helper for recreating a guest-to-host loopback connection.
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

function connect(endpoint, { serial, state, run }) {
  const url = new URL(endpoint);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port ||
      url.pathname !== '/' || url.search || url.hash || url.username || url.password)
    throw new Error('Expected the pinned loopback listener endpoint');
  const port = `tcp:${url.port}`;
  if (!serial && state) {
    if (!/^10\.0\.2\.\d{1,3}$/.test(state.AdbHost) || Number(state.AdbHost.split('.')[3]) > 255 ||
        !Number.isInteger(state.AdbPort) || state.AdbPort < 1 || state.AdbPort > 65535)
      throw new Error('Invalid task MuMu ADB address');
    serial = `${state.AdbHost}:${state.AdbPort}`;
    run(['connect', serial]);
  }
  const devices = run(['devices']).split(/\r?\n/)
    .map(line => /^(\S+)\s+device(?:\s|$)/.exec(line)).filter(Boolean).map(match => match[1]);
  if (!serial) {
    if (devices.length !== 1)
      throw new Error('Start the ForeverEden emulator first; with multiple devices, set ANDROID_SERIAL');
    [serial] = devices;
  }
  if (!devices.includes(serial)) throw new Error(`ForeverEden emulator ${serial} is not ready; start MuMu first`);
  const adb = args => run(['-s', serial, ...args]);
  if (!adb(['shell', 'pm', 'list', 'packages', 'games.fed.anothereden'])
      .split(/\r?\n/).includes('package:games.fed.anothereden'))
    throw new Error(`The private ForeverEden app is not installed on ${serial}`);
  adb(['reverse', port, port]);
  if (!adb(['reverse', '--list']).split(/\r?\n/).some(line => {
    const fields = line.trim().split(/\s+/);
    return fields.length === 3 && fields[1] === port && fields[2] === port;
  })) throw new Error('ADB did not confirm the listener port mapping');
  return { serial, message: `ForeverEden: ${serial} ${port} -> ${endpoint}` };
}

module.exports = { connect };
if (require.main === module) {
  try {
    const { loadRuntime } = require('./forevereden_server.cjs');
    const endpoint = loadRuntime().manifest.identity.endpoint;
    const stateFile = path.join(process.env.ProgramFiles || 'C:\\Program Files',
      'Netease', 'MuMuPlayerARM', 'vms', 'vm2.gmadoa', 'misc', 'state.json');
    // This is the existing isolated task instance, not the user's other MuMu profiles.
    const state = !process.env.ANDROID_SERIAL && process.platform === 'win32' && fs.existsSync(stateFile)
      ? JSON.parse(fs.readFileSync(stateFile, 'utf8').replace(/^\uFEFF/, '')) : null;
    const connection = connect(endpoint, {
      serial: process.env.ANDROID_SERIAL, state,
      run: args => execFileSync(process.env.ADB || 'adb', args,
        { encoding: 'utf8', timeout: 10000, maxBuffer: 1024 * 1024, windowsHide: true }).trim(),
    });
    console.log(connection.message);
  } catch (error) {
    console.error(`ForeverEden connection failed: ${error.message}`);
    process.exitCode = 1;
  }
}
