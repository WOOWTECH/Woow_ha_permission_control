() => {
  const ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });
  const result = {
    selectedTheme: ha.hass.selectedTheme,
    themeNames: Object.keys(ha.hass.themes?.themes || {}).slice(0, 15),
    defaultTheme: ha.hass.themes?.default_theme
  };
  return JSON.stringify(result);
}
