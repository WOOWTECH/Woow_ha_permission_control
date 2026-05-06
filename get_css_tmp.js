() => {
  const result = {};
  const root = document.documentElement;
  const ha = document.querySelector('home-assistant');
  const props = ["--sidebar-background-color", "--sidebar-selected-text-color", "--ha-card-background", "--primary-color", "--primary-text-color", "--primary-background-color", "--card-background-color", "--app-header-background-color"];
  for (const prop of props) {
    result[prop] = getComputedStyle(root).getPropertyValue(prop).trim()
      || (ha ? getComputedStyle(ha).getPropertyValue(prop).trim() : '') || '(not set)';
  }
  try {
    const sidebar = ha && ha.shadowRoot ? ha.shadowRoot.querySelector('ha-sidebar') : null;
    const menu = sidebar && sidebar.shadowRoot ? sidebar.shadowRoot.querySelector('.menu') : null;
    if (menu) result['_sidebar_actual_bg'] = getComputedStyle(menu).backgroundColor;
  } catch(e) {}
  return JSON.stringify(result);
}