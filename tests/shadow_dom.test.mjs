/**
 * Unit tests for the shadow-tree search the Filters use to reach rendered
 * Home Assistant content.
 *
 * Run:  node --test tests/shadow_dom.test.mjs
 *
 * Pure-function tests: the "DOM" here is plain objects with `localName`,
 * `children` and `shadowRoot`, which is the whole surface the search touches.
 * The trees below are the two element hierarchies Home Assistant has actually
 * shipped — the point of the search is that one traversal covers both, and
 * whatever the next one is called.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  findByLocalName,
  findInShadowTree,
} from "../custom_components/ha_permission_manager/frontend/shadow_dom.js";

/** An element-alike: light children in `children`, shadow children in `shadowRoot.children`. */
const el = (localName, { children = [], shadow = null } = {}) => ({
  localName,
  children,
  shadowRoot: shadow === null ? null : { children: shadow },
});

/**
 * Home Assistant 2026.7.2, as measured on 192.168.2.6 for issue #10:
 * `partial-panel-resolver` has no shadow root at all and the dashboard element
 * is `ha-panel-home`.
 */
const ha_2026_7 = () =>
  el("body", {
    children: [
      el("home-assistant", {
        shadow: [
          el("home-assistant-main", {
            shadow: [
              el("ha-drawer", {
                children: [
                  el("ha-sidebar", { shadow: [el("ha-md-list")] }),
                  el("partial-panel-resolver", {
                    children: [el("ha-panel-home", { shadow: [el("hui-root")] })],
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
    ],
  });

/** The hierarchy the hard-coded walk was written against. */
const ha_legacy = () =>
  el("body", {
    children: [
      el("home-assistant", {
        shadow: [
          el("home-assistant-main", {
            shadow: [
              el("ha-drawer", {
                children: [
                  el("partial-panel-resolver", {
                    shadow: [el("ha-panel-lovelace", { shadow: [el("hui-root")] })],
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
    ],
  });

test("hui-root is found under ha-panel-home, where the fixed walk gave up", () => {
  const found = findByLocalName(ha_2026_7(), "hui-root");
  assert.equal(found?.localName, "hui-root");
});

test("the same search still finds hui-root under ha-panel-lovelace", () => {
  const found = findByLocalName(ha_legacy(), "hui-root");
  assert.equal(found?.localName, "hui-root");
});

test("a host with no shadow root is stepped over, not treated as the end", () => {
  // The exact break in issue #10: partial-panel-resolver.shadowRoot is null,
  // and the panel hangs off it as a light child.
  const tree = el("root", {
    children: [el("partial-panel-resolver", { children: [el("hui-root")] })],
  });
  assert.equal(findByLocalName(tree, "hui-root")?.localName, "hui-root");
});

test("a panel this version has never heard of is still searched through", () => {
  const tree = el("body", {
    children: [el("home-assistant", { shadow: [el("ha-panel-whatever-is-next", { shadow: [el("hui-root")] })] })],
  });
  assert.equal(findByLocalName(tree, "hui-root")?.localName, "hui-root");
});

test("no match returns null rather than throwing", () => {
  const tree = el("body", { children: [el("home-assistant", { shadow: [el("ha-panel-config")] })] });
  assert.equal(findByLocalName(tree, "hui-root"), null);
});

test("an absent root is null, not a crash", () => {
  assert.equal(findByLocalName(null, "hui-root"), null);
  assert.equal(findByLocalName(undefined, "hui-root"), null);
  assert.equal(findInShadowTree(null, () => true), null);
});

test("the search is breadth-first, so the shallowest match wins", () => {
  const deep = el("hui-root", { children: [] });
  const shallow = el("hui-root", { children: [] });
  const tree = el("body", {
    children: [el("a", { children: [el("b", { children: [deep] })] }), el("c", { children: [shallow] })],
  });
  assert.equal(findByLocalName(tree, "hui-root"), shallow);
});

test("the root itself can be the match", () => {
  const root = el("hui-root");
  assert.equal(findByLocalName(root, "hui-root"), root);
});

test("either of two names matches, so a rename does not have to be a release", () => {
  const tree = el("body", { children: [el("hui-root-next")] });
  assert.equal(findByLocalName(tree, ["hui-root", "hui-root-next"])?.localName, "hui-root-next");
});

test("the node budget bounds the walk instead of scanning a whole dashboard", () => {
  const filler = Array.from({ length: 50 }, (_, i) => el(`card-${i}`));
  const tree = el("body", { children: [...filler, el("hui-root")] });

  assert.equal(findByLocalName(tree, "hui-root", { maxNodes: 10 }), null);
  assert.equal(findByLocalName(tree, "hui-root", { maxNodes: 200 })?.localName, "hui-root");
});

test("a predicate can match on more than the name", () => {
  const wanted = { localName: "hui-root", children: [], shadowRoot: { children: [] } };
  const decoy = el("hui-root"); // no shadow root: not yet rendered
  const tree = el("body", { children: [decoy, wanted] });

  const found = findInShadowTree(tree, (node) => node.localName === "hui-root" && !!node.shadowRoot);
  assert.equal(found, wanted);
});

test("nodes without a localName, such as text nodes, are skipped", () => {
  const tree = el("body", { children: [{ children: [] }, el("hui-root")] });
  assert.equal(findByLocalName(tree, "hui-root")?.localName, "hui-root");
});
