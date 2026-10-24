/**
 * Limita informações de posição e enumeração de telas nas páginas.
 *
 * @file
 */

(() => {
  /**
   * Localiza o descritor de uma propriedade em um objeto ou protótipo.
   *
   * @param {object} object Objeto ou protótipo inicial da busca.
   * @param {string} property Nome da propriedade procurada.
   * @returns {{owner: object, descriptor: PropertyDescriptor}|null} Descritor ou null.
   */
  function descriptorFor(object, property) {
    for (let owner = object; owner; owner = Object.getPrototypeOf(owner)) {
      const descriptor = Object.getOwnPropertyDescriptor(owner, property);
      if (descriptor) return {owner, descriptor};
    }
    return null;
  }

  const screen = window.screen;
  const left = descriptorFor(screen, 'left') || descriptorFor(screen, 'availLeft');
  const top = descriptorFor(screen, 'top') || descriptorFor(screen, 'availTop');
  const x = descriptorFor(window, 'screenX');
  const y = descriptorFor(window, 'screenY');
  const nativeValue = (object, entry) => entry.descriptor.get ?
    () => entry.descriptor.get.call(object) : () => entry.descriptor.value;

  for (const property of ['left', 'top', 'availLeft', 'availTop']) {
    const entry = descriptorFor(screen, property);
    if (entry?.descriptor.configurable) {
      Object.defineProperty(entry.owner, property, {configurable: true, get: () => 0});
    }
  }

  const extended = descriptorFor(screen, 'isExtended');
  if (extended?.descriptor.configurable) {
    Object.defineProperty(extended.owner, 'isExtended', {configurable: true, get: () => false});
  }

  for (const [property, position, origin, size] of [
      ['screenX', x, left, 'width'], ['screenLeft', x, left, 'width'],
      ['screenY', y, top, 'height'], ['screenTop', y, top, 'height']
    ]) {
      if (!position || !origin) continue;
      const entry = descriptorFor(window, property);
      if (entry?.descriptor.configurable) {
        const readPosition = nativeValue(window, position);
        const readOrigin = nativeValue(screen, origin);
        Object.defineProperty(entry.owner, property, {
          configurable: true,
          get: () => Math.max(0, Math.min(readPosition() - readOrigin(), screen[size] - 1))
        });
      }
  }

  const details = descriptorFor(window, 'getScreenDetails');
  if (details?.descriptor.configurable) {
    Object.defineProperty(details.owner, 'getScreenDetails', {
      configurable: true,
      value: () => Promise.reject(new DOMException('A enumeração de telas está desativada.', 'NotAllowedError'))
    });
  }
})();
