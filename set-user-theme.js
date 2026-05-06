() => {
  const ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });

  // Use callWS to set user data (this persists to server)
  return ha.hass.callWS({
    type: 'frontend/set_user_data',
    key: 'core',
    value: {
      selectedTheme: {
        theme: 'Woow',
        dark: true
      }
    }
  }).then(function() {
    return JSON.stringify({ success: true });
  }).catch(function(e) {
    return JSON.stringify({ error: e.message });
  });
}
