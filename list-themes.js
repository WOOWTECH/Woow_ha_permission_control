() => {
  const ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return JSON.stringify({ error: 'no-hass' });
  var themes = ha.hass.themes || {};
  var names = Object.keys(themes.themes || {});
  var defaultTheme = themes.default_theme;
  var darkMode = themes.darkMode;
  return JSON.stringify({
    count: names.length,
    names: names,
    defaultTheme: defaultTheme,
    darkMode: darkMode,
    selectedTheme: ha.hass.selectedTheme
  });
}
