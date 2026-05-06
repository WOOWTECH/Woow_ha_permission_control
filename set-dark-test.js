() => {
  const ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });

  // Step 1: Set system default theme
  const p1 = ha.hass.callService('frontend', 'set_theme', {
    name: 'Woow',
    mode: 'dark'
  });

  // Step 2: Also set user preference to dark
  const p2 = ha.hass.connection.sendMessagePromise({
    type: 'frontend/set_user_data',
    key: 'core',
    value: {
      selectedTheme: { theme: 'Woow', dark: true }
    }
  });

  return Promise.all([p1, p2]).then(function() {
    return JSON.stringify({ success: true, method: 'combined' });
  }).catch(function(e) {
    return JSON.stringify({ error: e.message });
  });
}
