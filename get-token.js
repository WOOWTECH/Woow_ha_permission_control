() => {
  const ha = document.querySelector('home-assistant');
  if (!ha || !ha.hass) return 'no-hass';
  return ha.hass.auth.data.access_token;
}
