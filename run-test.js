async (page) => {
  const THEMES = ['Woow', 'Frosted Glass', 'Google Theme'];
  const MODES = ['light', 'dark'];
  const PANELS = [
    { name: 'PM', url: '/ha_permission_manager' },
    { name: 'CP', url: '/ha-control-panel' },
    { name: 'AC', url: '/area-control' },
    { name: 'LC', url: '/label-control' },
  ];

  const CSS_PROPS = [
    '--sidebar-background-color',
    '--sidebar-selected-text-color',
    '--ha-card-background',
    '--primary-color',
    '--primary-text-color',
    '--primary-background-color',
    '--card-background-color',
    '--app-header-background-color',
  ];

  const results = [];
  const SCREENSHOT_DIR = '/tmp/ha-theme-test/screenshots';

  for (const theme of THEMES) {
    for (const mode of MODES) {
      // Set theme
      const setResult = await page.evaluate(({ theme, mode }) => {
        try {
          const ha = document.querySelector('home-assistant');
          if (!ha || !ha.hass) return 'no-hass';
          ha.hass.connection.sendMessage({
            type: 'frontend/set_user_data',
            key: 'core',
            value: { selectedTheme: { theme, dark: mode === 'dark' }, selectedLanguage: null }
          });
          return 'ok';
        } catch (e) { return e.message; }
      }, { theme, mode });

      console.log(`\n=== Theme: ${theme} | Mode: ${mode} | Result: ${setResult} ===`);
      await page.waitForTimeout(2000);
      await page.reload({ waitUntil: 'networkidle', timeout: 15000 });
      await page.waitForTimeout(3000);

      for (const panel of PANELS) {
        await page.goto(`http://localhost:15124${panel.url}`, { waitUntil: 'networkidle', timeout: 15000 });
        await page.waitForTimeout(2500);

        // Screenshot
        const filename = `${theme.replace(/\s+/g, '_')}_${mode}_${panel.name}.png`;
        await page.screenshot({ path: `${SCREENSHOT_DIR}/${filename}`, fullPage: false });

        // Extract CSS
        const css = await page.evaluate((props) => {
          const result = {};
          const root = document.documentElement;
          const ha = document.querySelector('home-assistant');
          for (const prop of props) {
            result[prop] = getComputedStyle(root).getPropertyValue(prop).trim()
              || (ha ? getComputedStyle(ha).getPropertyValue(prop).trim() : '') || '(not set)';
          }
          try {
            const sidebar = ha?.shadowRoot?.querySelector('ha-sidebar');
            const menu = sidebar?.shadowRoot?.querySelector('.menu');
            if (menu) result['_sidebar_actual_bg'] = getComputedStyle(menu).backgroundColor;
          } catch(e) {}
          return result;
        }, CSS_PROPS);

        results.push({ theme, mode, panel: panel.name, screenshot: filename, css });

        const primary = css['--primary-color'];
        const cardBg = css['--ha-card-background'] || css['--card-background-color'];
        const status = primary && primary !== '(not set)' ? 'OK' : 'CHECK';
        console.log(`  ${panel.name}: ${status} | primary=${primary} | card-bg=${cardBg}`);
      }
    }
  }

  // Return results as JSON string (we'll capture from console)
  const jsonStr = JSON.stringify(results, null, 2);
  console.log('\n===RESULTS_JSON_START===');
  console.log(jsonStr);
  console.log('===RESULTS_JSON_END===');
  return `Completed ${results.length} tests`;
}
