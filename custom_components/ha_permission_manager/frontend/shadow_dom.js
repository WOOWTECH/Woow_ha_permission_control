/**
 * HA Permission Manager - Shadow-tree search
 *
 * Finding rendered Home Assistant content, without naming the path to it.
 *
 * Home Assistant's element hierarchy is not an API. Between releases a host
 * loses its shadow root, a panel element is renamed, a wrapper appears — and a
 * traversal that spells the hierarchy out returns early and silently, which is
 * exactly how issue #10 went unnoticed. So a Filter names the element it wants
 * and lets this module look for it.
 *
 * The lovelace filter is the only caller so far. The sidebar filter and the
 * Access Denied Filter still spell out walks of their own, to `ha-sidebar` and
 * `ha-drawer`; those walks currently work, and converting them is its own
 * change on files issue #6 is already about. See docs/adr/0005.
 *
 * Pure: the only thing it touches is `localName`, `children` and `shadowRoot`,
 * which is why it can be unit tested (tests/shadow_dom.test.mjs) rather than
 * only observed in a live browser.
 *
 * Loaded as an ES module — Home Assistant pulls the Filters in with import().
 */

/**
 * How many nodes one search may look at.
 *
 * A rendered dashboard is thousands of nodes deep in cards, and the Filters
 * search on DOM mutations. The elements they look for sit within a handful of
 * levels of the document, so a budget this size is reached only when the
 * element is not there at all — where the answer is "no" either way.
 */
export const DEFAULT_MAX_NODES = 2000;

/** The children of a node, from its shadow root first and then its light DOM. */
function childrenOf(node) {
  const shadowChildren = node.shadowRoot ? node.shadowRoot.children : null;
  return [shadowChildren, node.children];
}

/**
 * The first element in `root`'s tree that `matches`, searching shadow roots.
 *
 * Breadth-first, so the shallowest match wins: with two candidates the one
 * nearer the document is the one Home Assistant is currently rendering.
 *
 * @param {Element|null|undefined} root where to start; the root itself can match
 * @param {(node: Element) => boolean} matches
 * @param {{maxNodes?: number}} [options]
 * @returns {Element|null} null when there is no match within the node budget
 */
export function findInShadowTree(root, matches, { maxNodes = DEFAULT_MAX_NODES } = {}) {
  if (!root) return null;

  const queue = [root];
  let visited = 0;

  while (queue.length > 0) {
    const node = queue.shift();
    if (!node) continue;
    if (++visited > maxNodes) return null;

    if (matches(node)) return node;

    for (const list of childrenOf(node)) {
      if (!list) continue;
      for (let i = 0; i < list.length; i++) {
        queue.push(list[i]);
      }
    }
  }

  return null;
}

/**
 * The first element in `root`'s tree with one of the given tag names.
 *
 * @param {Element|null|undefined} root
 * @param {string|string[]} names lower-case tag names, e.g. "hui-root"
 * @param {{maxNodes?: number}} [options]
 * @returns {Element|null}
 */
export function findByLocalName(root, names, options) {
  const wanted = Array.isArray(names) ? names : [names];
  return findInShadowTree(
    root,
    (node) => !!node.localName && wanted.includes(node.localName),
    options,
  );
}
