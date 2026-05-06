() => {
  const ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });

  // Use callWS which properly handles the response
  return ha.hass.connection.sendMessagePromise({
    type: 'frontend/set_user_data',
    key: 'core',
    value: {
      selectedTheme: { theme: 'Woow' }
    }
  }).then(function(r) {
    return JSON.stringify({ success: true, result: r });
  }).catch(function(e) {
    return JSON.stringify({ error: e.message });
  });
}
