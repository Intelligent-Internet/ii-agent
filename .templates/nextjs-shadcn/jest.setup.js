// Optional: configure or set up a testing framework before each test.
// If you delete this file, remove `setupFilesAfterEnv` from `jest.config.js`
// Used for **tests**/testing-library.js
// Learn more: https://github.com/testing-library/jest-dom
// import '@testing-library/jest-dom'

// Add global polyfills for Node.js environment
global.TextEncoder = require('util').TextEncoder;
global.TextDecoder = require('util').TextDecoder;

// Add MessagePort and MessageChannel polyfills (required for undici)
if (typeof global.MessagePort === 'undefined') {
  const { MessagePort, MessageChannel } = require('worker_threads');
  global.MessagePort = MessagePort;
  global.MessageChannel = MessageChannel;
}

// Add ReadableStream polyfill (required for undici)
if (typeof global.ReadableStream === 'undefined') {
  const { ReadableStream } = require('stream/web');
  global.ReadableStream = ReadableStream;
}

// Add WritableStream polyfill (often needed alongside ReadableStream)
if (typeof global.WritableStream === 'undefined') {
  const { WritableStream } = require('stream/web');
  global.WritableStream = WritableStream;
}

// Add TransformStream polyfill
if (typeof global.TransformStream === 'undefined') {
  const { TransformStream } = require('stream/web');
  global.TransformStream = TransformStream;
}

// Add polyfill for Request API
if (typeof global.Request === 'undefined') {
  const { Request } = require('undici');
  global.Request = Request;
}

// Add polyfill for Response API (often needed alongside Request)
if (typeof global.Response === 'undefined') {
  const { Response } = require('undici');
  global.Response = Response;
}

// Add polyfill for fetch API (if not already available)
if (typeof global.fetch === 'undefined') {
  const { fetch } = require('undici');
  global.fetch = fetch;
}

// Add Headers polyfill (often needed with fetch)
if (typeof global.Headers === 'undefined') {
  const { Headers } = require('undici');
  global.Headers = Headers;
}