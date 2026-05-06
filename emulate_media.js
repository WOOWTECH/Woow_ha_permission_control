async (page) => {
      await page.emulateMedia({ colorScheme: 'dark' });
      return 'dark';
    }