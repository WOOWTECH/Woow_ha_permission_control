async (page) => {
  await page.emulateMedia({ colorScheme: 'light' });
  return 'light mode enabled';
}
