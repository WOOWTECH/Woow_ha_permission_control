() => {
  var ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return 'no-hass';
  ha.hass.callService('frontend', 'set_theme', { name: 'default' });
  ha.hass.callWS({
    type: 'frontend/set_user_data',
    key: 'core',
    value: { selectedTheme: { theme: '' } }
  });
  return 'reset';
}