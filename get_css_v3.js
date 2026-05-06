() => {
  var result = {};
  var root = document.documentElement;
  var ha = document.querySelector('home-assistant');
  var props = ["--sidebar-background-color", "--sidebar-selected-text-color", "--ha-card-background", "--primary-color", "--primary-text-color", "--primary-background-color", "--card-background-color", "--app-header-background-color"];
  for (var i = 0; i < props.length; i++) {
    var prop = props[i];
    result[prop] = getComputedStyle(root).getPropertyValue(prop).trim()
      || (ha ? getComputedStyle(ha).getPropertyValue(prop).trim() : '') || '(not set)';
  }
  try {
    var sidebar = ha && ha.shadowRoot ? ha.shadowRoot.querySelector('ha-sidebar') : null;
    var menu = sidebar && sidebar.shadowRoot ? sidebar.shadowRoot.querySelector('.menu') : null;
    if (menu) result['_sidebar_actual_bg'] = getComputedStyle(menu).backgroundColor;
  } catch(e) {}
  return JSON.stringify(result);
}