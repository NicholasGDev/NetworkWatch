const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

let origin = -1920;
let position = -1400;
const screen = Object.create({
  get left() { return origin; },
  get top() { return 0; },
  get availLeft() { return origin; },
  get availTop() { return 0; },
  get isExtended() { return true; }
});
const window = Object.create({
  get screenX() { return position; },
  get screenY() { return 100; },
  get screenLeft() { return position; },
  get screenTop() { return 100; }
});
window.screen = screen;
vm.runInNewContext(fs.readFileSync('firefox-extension\\screen.js', 'utf8'), {window});
assert.equal(screen.left, 0);
assert.equal(screen.availLeft, 0);
assert.equal(screen.isExtended, false);
assert.equal(window.screenX, 520);
assert.equal(window.screenLeft, 520);
position = -1300;
assert.equal(window.screenX, 620);
origin = 1920;
position = 2200;
assert.equal(window.screenX, 280);
console.log('screen normalization OK');
