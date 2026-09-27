'use strict';
const assert = require('node:assert/strict');
const { connect } = require('./forevereden_connect.cjs');
const endpoint = 'http://127.0.0.1:28765';
function check({ serial, state, devices = ['10.0.2.207:5555'], installed = true,
                 mapping = 'host-13 tcp:28765 tcp:28765', reverseError = false } = {}) {
  const calls = [];
  const run = args => {
    calls.push(args);
    if (args[0] === 'connect') return 'connected';
    if (args[0] === 'devices') return 'List of devices attached\n' + devices.map(s => `${s}\tdevice`).join('\n');
    assert.equal(args[0], '-s');
    assert(devices.includes(args[1]));
    if (args[2] === 'shell') {
      assert.deepEqual(args.slice(2), ['shell', 'pm', 'list', 'packages', 'games.fed.anothereden']);
      return installed ? 'package:games.fed.anothereden' : 'package:games.wfs.anothereden';
    }
    assert.equal(args[2], 'reverse');
    if (args[3] === '--list') return mapping;
    assert.deepEqual(args.slice(3), ['tcp:28765', 'tcp:28765']);
    if (reverseError) throw new Error('reverse failed');
    return '28765';
  };
  const result = connect(endpoint, { serial, state, run });
  assert.equal(result.serial, serial || '10.0.2.207:5555');
  assert.match(result.message, /tcp:28765 -> http:\/\/127\.0\.0\.1:28765$/);
  return calls;
}
assert.equal(check().length, 4);
assert.deepEqual(check({ state: { AdbHost: '10.0.2.207', AdbPort: 5555 } })[0], ['connect', '10.0.2.207:5555']);
check({ serial: '10.0.2.207:5555', devices: ['phone', '10.0.2.207:5555'] });
assert.throws(() => check({ devices: [] }), /Start the ForeverEden emulator/);
assert.throws(() => check({ devices: ['phone', 'other'] }), /ANDROID_SERIAL/);
assert.throws(() => check({ serial: 'offline' }), /not ready/);
assert.throws(() => check({ installed: false }), /not installed/);
assert.throws(() => check({ mapping: 'host-13 tcp:28765 tcp:9999' }), /did not confirm/);
assert.throws(() => check({ reverseError: true }), /reverse failed/);
assert.throws(() => check({ state: { AdbHost: '10.0.2.999', AdbPort: 5555 } }), /Invalid/);
assert.throws(() => connect('http://example.com:28765', {}), /loopback/);
console.log('PASS: automatic MuMu connection, device selection, exact port mapping and failure paths');
