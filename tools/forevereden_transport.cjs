'use strict';
// Original Android AES/zlib framing; native fixture checks retained in the focused test.
const { createCipheriv, createDecipheriv, createHash } = require('node:crypto');
const { deflateSync, inflateSync } = require('node:zlib');
const { constants: bufferConstants } = require('node:buffer');
const MAX_NODES = 2_000_000;

function validate(data, key, iv, limits, inputKind) {
  if (!Buffer.isBuffer(data) || !Buffer.isBuffer(key) || key.length !== 32 ||
      !Buffer.isBuffer(iv) || iv.length !== 16) throw new TypeError('Expected buffers, a 32-byte key and a 16-byte IV');
  for (const kind of ['plaintext', 'ciphertext']) {
    const value = limits?.[kind];
    if (!Number.isSafeInteger(value) || value < 1 || value > bufferConstants.MAX_LENGTH)
      throw new RangeError(`Explicit ${kind} size limit required`);
  }
  if (data.length > limits[inputKind]) throw new RangeError(`${inputKind} exceeds limit`);
}

function encryptBody(plaintext, key, iv, limits) {
  validate(plaintext, key, iv, limits, 'plaintext');
  if (!plaintext.length) return Buffer.alloc(0);
  const compressed = deflateSync(plaintext, { maxOutputLength: limits.ciphertext });
  // Original routine adds no extra block when the zlib stream is already aligned.
  const padding = (-compressed.length) & 15;
  if (compressed.length + padding > limits.ciphertext) throw new RangeError('ciphertext exceeds limit');
  const cipher = createCipheriv('aes-256-cbc', key, iv);
  cipher.setAutoPadding(false);
  return Buffer.concat([cipher.update(Buffer.concat([compressed, Buffer.alloc(padding, padding)])), cipher.final()]);
}

function decryptBody(ciphertext, key, iv, limits) {
  validate(ciphertext, key, iv, limits, 'ciphertext');
  if (!ciphertext.length) return Buffer.alloc(0);
  if (ciphertext.length % 16) throw new RangeError('Ciphertext must contain complete AES blocks');
  const decipher = createDecipheriv('aes-256-cbc', key, iv);
  decipher.setAutoPadding(false);
  const packed = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  const { buffer, engine } = inflateSync(packed, { info: true, maxOutputLength: limits.plaintext });
  const consumed = engine.bytesWritten;
  const padding = (-consumed) & 15;
  const trailing = packed.subarray(consumed);
  const originalPadding = trailing.length === padding && trailing.every(byte => byte === padding);
  const fullBlockPadding = padding === 0 && trailing.length === 16 && trailing.every(byte => byte === 16);
  if (!originalPadding && !fullBlockPadding)
    throw new Error('Noncanonical trailing data after zlib stream');
  return buffer;
}

// The startup response uses only JSON-shaped MessagePack values. No extensions.
function encodeMsgpack(value, maxBytes = 8 * 1024 * 1024) {
  const parts = []; let size = 0, nodes = 0;
  function emit(b) { size += b.length; if (size > maxBytes) throw new RangeError('MessagePack output bound'); parts.push(b); }
  function number(tag, length, method, n) { const b = Buffer.alloc(length + 1); b[0] = tag; b[method](n, 1); emit(b); }
  function length(n, fix, small, medium, large) {
    if (n < fix) emit(Buffer.from([small + n]));
    else if (medium !== null && n <= 65535) number(medium, 2, 'writeUInt16BE', n);
    else number(large, 4, 'writeUInt32BE', n);
  }
  function visit(v, depth) {
    if (++nodes > MAX_NODES || depth > 32) throw new RangeError('MessagePack structure bound');
    if (v === null) return emit(Buffer.from([0xc0]));
    if (typeof v === 'boolean') return emit(Buffer.from([v ? 0xc3 : 0xc2]));
    if (typeof v === 'string') {
      const b = Buffer.from(v); if (b.length > 1024 * 1024) throw new RangeError('String bound');
      if (b.length < 32) emit(Buffer.from([0xa0 + b.length]));
      else if (b.length <= 255) number(0xd9, 1, 'writeUInt8', b.length);
      else length(b.length, 0, 0, 0xda, 0xdb);
      return emit(b);
    }
    if (typeof v === 'number') {
      if (!Number.isFinite(v)) throw new RangeError('Nonfinite number');
      if (!Number.isInteger(v)) return number(0xcb, 8, 'writeDoubleBE', v);
      if (!Number.isSafeInteger(v)) throw new RangeError('Unsafe integer');
      if (v >= 0 && v < 128 || v < 0 && v >= -32) return emit(Buffer.from([v & 255]));
      if (v >= 0 && v <= 255) return number(0xcc, 1, 'writeUInt8', v);
      if (v >= 0 && v <= 65535) return number(0xcd, 2, 'writeUInt16BE', v);
      if (v >= 0 && v <= 0xffffffff) return number(0xce, 4, 'writeUInt32BE', v);
      if (v < 0 && v >= -128) return number(0xd0, 1, 'writeInt8', v);
      if (v < 0 && v >= -32768) return number(0xd1, 2, 'writeInt16BE', v);
      if (v < 0 && v >= -2147483648) return number(0xd2, 4, 'writeInt32BE', v);
      return number(v >= 0 ? 0xcf : 0xd3, 8, v >= 0 ? 'writeBigUInt64BE' : 'writeBigInt64BE', BigInt(v));
    }
    if (Array.isArray(v)) {
      if (v.length > 100000) throw new RangeError('Array bound');
      length(v.length, 16, 0x90, 0xdc, 0xdd);
      for (const item of v) visit(item, depth + 1);
      return;
    }
    if (typeof v !== 'object' || Object.getPrototypeOf(v) !== Object.prototype) throw new TypeError('Unsupported MessagePack value');
    const entries = Object.entries(v); if (entries.length > 100000) throw new RangeError('Map bound');
    length(entries.length, 16, 0x80, 0xde, 0xdf);
    for (const [k, item] of entries) { visit(k, depth + 1); visit(item, depth + 1); }
  }
  visit(value, 0);
  return Buffer.concat(parts, size);
}

function decodeMsgpack(input, maxBytes = 16 * 1024 * 1024) {
  if (!Buffer.isBuffer(input) || input.length > maxBytes) throw new RangeError('MessagePack input bound');
  let offset = 0, nodes = 0;
  function take(n) {
    if (!Number.isSafeInteger(n) || n < 0 || offset + n > input.length) throw new RangeError('Truncated MessagePack');
    const start = offset; offset += n; return start;
  }
  function length(bytes) {
    const at = take(bytes);
    return bytes === 1 ? input.readUInt8(at) : bytes === 2 ? input.readUInt16BE(at) : input.readUInt32BE(at);
  }
  function string(n) {
    if (n > 4 * 1024 * 1024) throw new RangeError('String bound');
    const value = input.toString('utf8', take(n), offset);
    if (Buffer.byteLength(value) !== n) throw new Error('Invalid UTF-8 string');
    return value;
  }
  function integer64(signed) {
    const at = take(8), value = signed ? input.readBigInt64BE(at) : input.readBigUInt64BE(at);
    if (value < BigInt(Number.MIN_SAFE_INTEGER) || value > BigInt(Number.MAX_SAFE_INTEGER)) throw new RangeError('Unsafe integer');
    return Number(value);
  }
  function array(n, depth) {
    if (n > 100000) throw new RangeError('Array bound');
    return Array.from({ length: n }, () => read(depth + 1));
  }
  function map(n, depth) {
    if (n > 100000) throw new RangeError('Map bound');
    const value = {};
    for (let i = 0; i < n; i++) {
      const key = read(depth + 1);
      if (typeof key !== 'string' || Object.hasOwn(value, key)) throw new Error('Invalid or duplicate map key');
      value[key] = read(depth + 1);
    }
    return value;
  }
  function read(depth) {
    if (++nodes > MAX_NODES || depth > 32) throw new RangeError('MessagePack structure bound');
    const tag = input[take(1)];
    if (tag <= 0x7f) return tag;
    if (tag >= 0xe0) return tag - 256;
    if ((tag & 0xe0) === 0xa0) return string(tag & 0x1f);
    if ((tag & 0xf0) === 0x90) return array(tag & 0x0f, depth);
    if ((tag & 0xf0) === 0x80) return map(tag & 0x0f, depth);
    switch (tag) {
      case 0xc0: return null;
      case 0xc2: return false;
      case 0xc3: return true;
      case 0xca: { const at = take(4), value = input.readFloatBE(at); if (!Number.isFinite(value)) throw new RangeError('Nonfinite number'); return value; }
      case 0xcb: { const at = take(8), value = input.readDoubleBE(at); if (!Number.isFinite(value)) throw new RangeError('Nonfinite number'); return value; }
      case 0xcc: return input.readUInt8(take(1));
      case 0xcd: return input.readUInt16BE(take(2));
      case 0xce: return input.readUInt32BE(take(4));
      case 0xcf: return integer64(false);
      case 0xd0: return input.readInt8(take(1));
      case 0xd1: return input.readInt16BE(take(2));
      case 0xd2: return input.readInt32BE(take(4));
      case 0xd3: return integer64(true);
      case 0xd9: return string(length(1));
      case 0xda: return string(length(2));
      case 0xdb: return string(length(4));
      case 0xdc: return array(length(2), depth);
      case 0xdd: return array(length(4), depth);
      case 0xde: return map(length(2), depth);
      case 0xdf: return map(length(4), depth);
      default: throw new Error(`Unsupported MessagePack tag 0x${tag.toString(16)}`);
    }
  }
  const value = read(0);
  if (offset !== input.length) throw new Error('Trailing MessagePack data');
  return value;
}

module.exports = { encryptBody, decryptBody, encodeMsgpack, decodeMsgpack };
