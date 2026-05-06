() => {
  var ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });

  // HA reads dark mode from themes.darkMode
  // We can force it by manipulating the frontend store
  // Use callWS to set user data with dark flag
  return ha.hass.callWS({
    type: 'frontend/set_user_data',
    key: 'core',
    value: {
      selectedTheme: { theme: 'Woow', dark: true }
    }
  }).then(function() {
    // Also fire the themes_updated event to trigger re-rendering
    return ha.hass.callService('frontend', 'set_theme', {
      name: 'Woow',
      mode: 'dark'
    });
  }).then(function() {
    return new Promise(function(resolve) {
      setTimeout(function() {
        var root = document.documentElement;
        var primary = getComputedStyle(root).getPropertyValue('--primary-color').trim();
        var bg = getComputedStyle(root).getPropertyValue('--primary-background-color').trim();
        var darkMode = ha.hass.themes ? ha.hass.themes.darkMode : 'unknown';
        resolve(JSON.stringify({
          success: true,
          primary: primary,
          bg: bg,
          darkMode: darkMode
        }));
      }, 2000);
    });
  }).catch(function(e) {
    return JSON.stringify({ error: e.message });
  });
}
