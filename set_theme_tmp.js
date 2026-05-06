() => {
  const ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });
  return ha.hass.callService('frontend', 'set_theme', {
    name: 'default',
    mode: 'light'
  }).then(function() {
    return JSON.stringify({ success: true });
  }).catch(function(e) {
    return JSON.stringify({ error: e.message });
  });
}