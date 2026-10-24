/**
 * Testa as proteções de API de tela da extensão Chrome.
 *
 * @file
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const manifest = JSON.parse(fs.readFileSync('chrome-extension\\manifest.json', 'utf8'));
const injection = manifest.content_scripts[0];
assert.equal(injection.world, 'MAIN');
assert.equal(injection.run_at, 'document_start');
assert.equal(injection.all_frames, true);
assert.equal(injection.match_origin_as_fallback, true);

let origin = -1920;
let position = -1400;
/**
 * Objeto Screen mínimo que reproduz propriedades extensíveis do navegador.
 */
class Screen {
  get availLeft() { return origin; }
  get availTop() { return 0; }
  get width() { return 1920; }
  get height() { return 1080; }
  get isExtended() { return true; }
}
/**
 * Janela simulada com posições e API de enumeração de telas.
 */
class Window {
  constructor() { this.screen = new Screen(); }
  get screenX() { return position; }
  get screenLeft() { return position; }
  get screenY() { return 100; }
  get screenTop() { return 100; }
  async getScreenDetails() { return {screens: [1, 2], currentScreen: 1}; }
}
const window = new Window();
vm.runInNewContext(fs.readFileSync('chrome-extension\\screen.js', 'utf8'), {window, DOMException});
assert.equal(window.screen.isExtended, false);
assert.equal(new Screen().isExtended, false);
assert.equal('left' in window.screen, false);
assert.equal(window.screen.availLeft, 0);
assert.equal(window.screenX, 520);
assert.equal(window.screenLeft, 520);
position = -1300;
assert.equal(window.screenX, 620);
origin = 1920;
position = 2200;
assert.equal(window.screenX, 280);
position = 6000;
assert.equal(window.screenX, 1919);
assert.equal(window.screenTop, 100);

(async () => {
  await assert.rejects(window.getScreenDetails(), {name: 'NotAllowedError'});
  await assert.rejects(Window.prototype.getScreenDetails.call(window), {name: 'NotAllowedError'});
  console.log('Chrome screen privacy OK');
})().catch((error) => { console.error(error); process.exitCode = 1; });
