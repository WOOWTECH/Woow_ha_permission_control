() => {
  const root = document.documentElement;
  const r = {};
  var props = ['--primary-color', '--primary-background-color', '--card-background-color', '--sidebar-background-color', '--primary-text-color'];
  for (var i = 0; i < props.length; i++) {
    r[props[i]] = getComputedStyle(root).getPropertyValue(props[i]).trim() || '(not set)';
  }
  return JSON.stringify(r);
}
