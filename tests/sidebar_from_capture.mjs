/**
 * The sidebar each identity would see, from a verify_issue_17.py capture.
 *
 * Run:  node tests/sidebar_from_capture.mjs < capture.json
 *
 * The decision comes from the shipped `filterPanels()`, imported out of
 * frontend/permission_policy.js. That is the whole point of shelling out to
 * node from a Python verification: a restatement of the rule in Python could
 * be wrong in the same direction as the change under test, and would then
 * agree with it and prove nothing.
 *
 * `currentPanel` is null on purpose. A panel kept as a routing anchor depends
 * on the URL the browser happens to be on, and this measures the Permission
 * decision, not where someone was standing when the capture ran.
 */
import { filterPanels } from "../custom_components/ha_permission_manager/frontend/permission_policy.js";

const capture = JSON.parse(await new Promise((resolve, reject) => {
  let text = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => (text += chunk));
  process.stdin.on("end", () => resolve(text));
  process.stdin.on("error", reject);
}));

const sidebars = {};

for (const [identity, data] of Object.entries(capture.identities)) {
  // The sidebar Filter hands an administrator the panel map untouched, so
  // there is nothing to compute: what Home Assistant sent is what they see.
  if (data.is_admin) {
    sidebars[identity] = [...data.panel_ids].sort();
    continue;
  }

  // filterPanels() reads only the keys of hass.panels, so a stand-in entry per
  // id carries everything the decision needs.
  const panels = Object.fromEntries(data.panel_ids.map((id) => [id, { url_path: id }]));
  const { panels: filtered } = filterPanels({
    panels,
    permissions: data.permissions,
    currentPanel: null,
  });
  sidebars[identity] = Object.keys(filtered).sort();
}

process.stdout.write(JSON.stringify(sidebars));
