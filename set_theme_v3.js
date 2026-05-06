() => {
  var ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });

  // Step 1: Set user preference (persists)
  var p1 = ha.hass.callWS({
    type: 'frontend/set_user_data',
    key: 'core',
    value: {
      selectedTheme: { theme: 'Google Theme', dark: true }
    }
  });

  // Step 2: Set system default theme (triggers immediate CSS update)
  var p2 = ha.hass.callService('frontend', 'set_theme', {
    name: 'Google Theme',
    mode: 'dark'
  });

  return Promise.all([p1, p2]).then(function() {
    // Wait for theme to apply
    return new Promise(function(resolve) {
      setTimeout(function() {
        var root = document.documentElement;
        var primary = getComputedStyle(root).getPropertyValue('--primary-color').trim();
        resolve(JSON.stringify({ success: true, primary: primary }));
      }, 3000);
    });
  }).catch(function(e) {
    return JSON.stringify({ error: e.message });
  });
}