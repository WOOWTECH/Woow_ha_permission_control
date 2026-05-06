() => {
  const ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });

  return ha.hass.callService('frontend', 'set_theme', {
    name: 'Woow',
    mode: 'dark'
  }).then(function() {
    // Wait a bit for theme to apply
    return new Promise(function(resolve) {
      setTimeout(function() {
        var root = document.documentElement;
        var primary = getComputedStyle(root).getPropertyValue('--primary-color').trim();
        var bg = getComputedStyle(root).getPropertyValue('--primary-background-color').trim();
        var text = getComputedStyle(root).getPropertyValue('--primary-text-color').trim();
        resolve(JSON.stringify({
          success: true,
          applied: { primary: primary, bg: bg, text: text }
        }));
      }, 2000);
    });
  }).catch(function(e) {
    return JSON.stringify({ error: e.message });
  });
}
