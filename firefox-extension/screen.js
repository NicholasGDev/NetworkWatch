(() => {
  const nativeScreen = window.screen;
  function nativeValue(object, property) {
    let owner = object;
    while (owner) {
      const descriptor = Object.getOwnPropertyDescriptor(owner, property);
      if (descriptor) {
        return descriptor.get ? () => descriptor.get.call(object) : () => descriptor.value;
      }
      owner = Object.getPrototypeOf(owner);
    }
    return () => undefined;
  }
  const left = nativeValue(nativeScreen, 'left');
  const top = nativeValue(nativeScreen, 'top');
  const screenX = nativeValue(window, 'screenX');
  const screenY = nativeValue(window, 'screenY');

  for (const property of ['left', 'top', 'availLeft', 'availTop']) {
    if (property in nativeScreen) {
      Object.defineProperty(nativeScreen, property, {
        configurable: true,
        get: () => 0
      });
    }
  }
  if ('isExtended' in nativeScreen) {
    Object.defineProperty(nativeScreen, 'isExtended', {
      configurable: true,
      get: () => false
    });
  }
  for (const [property, position, origin] of [
    ['screenX', screenX, left],
    ['screenLeft', screenX, left],
    ['screenY', screenY, top],
    ['screenTop', screenY, top]
  ]) {
    if (property in window) {
      const descriptor = Object.getOwnPropertyDescriptor(window, property);
      if (descriptor && !descriptor.configurable) continue;
      Object.defineProperty(window, property, {
        configurable: true,
        get: () => position() - origin()
      });
    }
  }
})();
