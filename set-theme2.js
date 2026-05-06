() => {
  const ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });

  // Try calling the frontend.set_theme service
  return ha.hass.callService('frontend', 'set_theme', {
    name: 'Woow',
    mode: 'light'
  }).then(function() {
    return JSON.stringify({ success: true, method: 'service_call' });
  }).catch(function(e) {
    return JSON.stringify({ error: e.message, method: 'service_call' });
  });
}
