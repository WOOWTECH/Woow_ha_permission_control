/**
 * What the frontend is allowed to call each layer, in its shipped prose (#22).
 *
 * Run:  node --test tests/console_vocabulary.test.mjs
 *
 * A console message is shipped prose that someone reads, so CONTEXT.md's
 * glossary binds it exactly as it binds the docs. The word at stake is
 * "overlay": the Loading overlay took it, and the entry that took it lists
 * "Access Denied overlay" under _Avoid_ — the Access Denied Filter renders a
 * panel element with its own header, not a cover over one.
 *
 * These read the shipped source as text, as tests/frontend_assets.test.mjs and
 * tests/loading_overlay.test.mjs do, because a console call is reached only by
 * the failure it reports and the module around it cannot be imported outside a
 * running Home Assistant.
 *
 * Read as text, and deliberately without a parser. An earlier draft walked
 * each `console.*(` call to its closing parenthesis to separate messages from
 * the machinery between them. It could be derailed by an apostrophe in a
 * comment inside a call — `ha_lovelace_filter.js` writes "Home Assistant's" in
 * prose one line from the message under test — and it failed at module scope,
 * taking every test here down with a complaint about parentheses. What is
 * below cannot run away: two regexes, neither of which can match past the line
 * it starts on.
 *
 * Scope is the frontend a browser is served. `docs/adr/` is out, on the
 * reasoning issue #22 gave for leaving ADR-0006 alone: an ADR is a dated
 * record of what was believed when it was written, not living text. ADR-0005
 * says "the overlay's check" of the Access Denied Filter and stays as it is.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const COMPONENT = path.join(REPO, "custom_components", "ha_permission_manager");
const FRONTEND = path.join(COMPONENT, "frontend");

const read = (...parts) => readFileSync(path.join(...parts), "utf8");

/** Every .js file served out of the frontend directory. */
const MODULES = readdirSync(FRONTEND).filter((name) => name.endsWith(".js"));

/**
 * A module's prose as a reader meets it, rather than as it is written.
 *
 * A shipped sentence is built by concatenation and wrapped to fit the column,
 * so "the Access Denied " and "page is the only layer" are two literals on two
 * lines. Dropping what sits between quotes, plus-signs and line breaks puts
 * the sentence back together, so a phrase can be looked for once instead of in
 * every spelling the wrapping might have given it. Comments come through the
 * same way, which is the point: the prose a maintainer reads is bound by the
 * glossary exactly as the prose a user reads is.
 */
const prose = (source) => source.replace(/["'`+]|\s+/g, " ").replace(/ +/g, " ");

/**
 * Every double-quoted string literal in a module, joined as it will be read.
 *
 * No frontend module escapes a quote inside a string, so a literal is whatever
 * sits between one quote and the next — no escape handling, and nothing that
 * can match past the line it starts on. A quote inside a comment pairs with
 * the next one and shifts what is read as a literal; the three in
 * ha_lovelace_filter.js are balanced pairs, which is why this stays aligned.
 * If that ever stops being true, the tests below fail loudly rather than
 * quietly pass on a shifted stream.
 */
const messages = (source) =>
  (source.match(/"[^"\n]*"/g) ?? [])
    .map((literal) => literal.slice(1, -1))
    .join("");

test("no frontend module writes the spelling CONTEXT.md forbids", () => {
  // The exact _Avoid_ entry, in code and comments alike. What this cannot
  // catch is the same mistake made without the two words touching — the
  // comment above showNoAccessMessage() said "where the overlay does not run"
  // and meant this same page. No regex finds that one; the next two tests pin
  // the sentence issue #22 was about, and a reader has to do the rest.
  for (const name of MODULES) {
    assert.doesNotMatch(
      prose(read(FRONTEND, name)),
      /access denied overlay/i,
      `${name} calls the Access Denied page an overlay`,
    );
  }
});

test("the unreachable-dashboard warning names the layer covering the content", () => {
  const warning = messages(read(FRONTEND, "ha_lovelace_filter.js"));

  assert.match(
    warning,
    /is denied for this user/,
    "the unreachable-dashboard warning is still there",
  );
  assert.match(
    warning,
    /the Access Denied page is the only layer covering this content/,
    "the warning names the Access Denied page, and no other layer",
  );
});

test("the unreachable-dashboard warning reads for one element name or several", () => {
  // DASHBOARD_ROOTS is interpolated into the sentence and today holds one
  // name. The clause has to survive the day it holds three, so it is rendered
  // here from the shipped template — separator included — rather than from a
  // copy of the wording living in this test.
  const source = read(FRONTEND, "ha_lovelace_filter.js");

  const roots = /const DASHBOARD_ROOTS = \[([^\]]*)\]/.exec(source);
  assert.ok(roots, "DASHBOARD_ROOTS is a literal array");
  const shipped = roots[1].match(/"[^"]+"/g).map((name) => name.slice(1, -1));

  const clause =
    /"([^"]*no <)"\s*\+\s*DASHBOARD_ROOTS\.join\("([^"]+)"\)\s*\+\s*"(>[^"]*)"/.exec(
      source,
    );
  assert.ok(clause, "the warning still names the elements it looked for");
  const [, prefix, separator, suffix] = clause;

  for (const names of [shipped, ["hui-root", "ha-panel-lovelace", "hui-view"]]) {
    const rendered = prefix + names.join(separator) + suffix;
    // "no <a> or <b> or <c> is on the page" — a list of alternatives under one
    // "no", which reads with a singular verb however long the list gets. The
    // comma-and-plural spelling this replaced ("no <a>, <b> was found") did
    // not, and neither did the tail that followed it: "taught the new one".
    assert.match(
      rendered,
      /^[^"]*no <[^<>]+>( or <[^<>]+>)* is on the page[^"]*$/,
      `reads wrong for ${names.length} element name(s): ${rendered}`,
    );
  }

  assert.doesNotMatch(
    messages(source),
    /taught the new one\b/,
    "the sentence does not promise a single replacement name",
  );
});

test("CONTEXT.md still reserves 'overlay' for the Loading overlay", () => {
  // If the glossary ever gives the word back, these tests are the thing to
  // delete — so they fail loudly rather than quietly outliving their reason.
  const context = read(REPO, "CONTEXT.md");
  const entry = /\*\*Loading overlay\*\*:[\s\S]*?_Avoid_: ([^\n]+)/.exec(context);

  assert.ok(entry, "CONTEXT.md has a Loading overlay entry with an _Avoid_ list");
  assert.ok(
    entry[1].includes("Access Denied overlay"),
    "'Access Denied overlay' is still a forbidden spelling",
  );
});
