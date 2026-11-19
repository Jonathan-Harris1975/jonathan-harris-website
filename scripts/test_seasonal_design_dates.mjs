import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const ui = readFileSync(new URL("../assets/js/site-ui.min.js", import.meta.url), "utf8");
const css = readFileSync(new URL("../assets/css/site.css", import.meta.url), "utf8");
const marker = '(()=>{"use strict";\nconst d=new Date()';
const index = ui.lastIndexOf(marker);
assert.ok(index >= 0, "seasonal calendar module must remain present");
const calendarModule = ui.slice(index);

function themedDate(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  const instant = new Date(year, month - 1, day, 12);
  class Clock extends Date {
    constructor(...args) {
      if (args.length) super(...args);
      else super(instant.getTime());
    }
    static now() { return instant.getTime(); }
  }
  const classes = new Set();
  const root = {
    dataset: {},
    classList: { add(name) { classes.add(name); } },
  };
  vm.runInNewContext(calendarModule, {
    Date: Clock, Math, document: { documentElement: root },
  });
  assert.ok(classes.has("seasonal-theme-ready"), "theme activation must remain automatic");
  return root.dataset;
}

test("all four seasons change at calendar boundaries", () => {
  for (const [date, season] of [
    ["2026-02-28", "winter"], ["2026-03-01", "spring"],
    ["2026-05-31", "spring"], ["2026-06-01", "summer"],
    ["2026-08-31", "summer"], ["2026-09-01", "autumn"],
    ["2026-11-30", "autumn"], ["2026-12-01", "winter"],
  ]) {
    assert.equal(themedDate(date).season, season, date);
    assert.ok(css.includes('data-season="' + season + '"'), "missing CSS for " + season);
  }
});

test("special event themes and their end boundaries are preserved", () => {
  for (const [date, event] of [
    ["2026-02-10", "safer-internet-day"],
    ["2026-02-14", "valentines"],
    ["2026-03-08", "international-womens-day"],
    ["2026-03-15", "mothering-sunday"],
    ["2026-03-17", "st-patricks-day"],
    ["2026-04-03", "easter"],
    ["2026-04-22", "earth-day"],
    ["2026-06-15", "pride-month"],
    ["2026-06-21", "fathers-day"],
    ["2026-10-31", "halloween"],
    ["2026-11-05", "bonfire-night"],
    ["2026-11-11", "remembrance"],
    ["2026-12-20", "christmas"],
    ["2026-12-30", "christmas"],
    ["2026-12-31", "new-year"],
    ["2027-01-02", "new-year"],
  ]) {
    assert.equal(themedDate(date).event, event, date);
    assert.ok(css.includes('data-event="' + event + '"'), "missing CSS for " + event);
  }
  assert.equal(themedDate("2027-01-03").event, undefined);
});

test("editorial refinements use existing seasonal-aware accent token", () => {
  const start = css.indexOf("JH-EDITORIAL-REFINEMENT-2026");
  assert.ok(start >= 0);
  const refinements = css.slice(start);
  assert.match(refinements, /outline:3px solid var\(--accent\)/);
  assert.match(refinements, /border-color:var\(--border\)/);
  assert.doesNotMatch(refinements, /#[0-9a-fA-F]{3,8}\b/, "no replacement palette in the new design layer");
});
// Browser-previewed navigation refinements must remain in the shared design layer.
test("book detail keeps the category breadcrumb instead of duplicating the trail", () => {
  assert.match(css, /body\.ebook-detail \.main:has\(\.breadcrumbs\)>\.jh-breadcrumbs\{display:none!important\}/);
});

test("compact editorial navigation links meet the 24px target minimum", () => {
  assert.match(css, /\.jh-breadcrumbs__item a,\.breadcrumbs a,\.featured-footer-note a\{display:inline-flex;align-items:center;min-height:24px\}/);
});
test("mobile consent layout retains both equal-width decisions and Customise, without changing palette", () => {
  const marker = "/* Mobile CookieYes layout:";
  const start = css.indexOf(marker);
  assert.ok(start >= 0, "CMP layout marker required");
  const rule = css.slice(start);
  assert.match(rule, /\[data-cky-tag="notice-buttons"\]\s*\{\s*display:grid!important/);
  assert.match(rule, /grid-template-columns:repeat\(2,minmax\(0,1fr\)\)/);
  assert.match(rule, /\[data-cky-tag="settings-button"\]\s*\{\s*grid-column:1\/-1/);
  assert.match(rule, /\[data-cky-tag="notice-buttons"\]>\[data-cky-tag\$="-button"\]\s*\{\s*order:0!important/);
  assert.doesNotMatch(rule, /\.cky-btn\b/, "use stable consent data roles, not vendor CSS classes");
  assert.doesNotMatch(rule, /display:\s*none|visibility:\s*hidden|(?:^|[;{])\s*(?:color|background(?:-color)?):/im);
});

test("catalogue mobile topic filters use the stable single-row rail and header", () => {
  const marker = "/* Keep the catalogue navigation stable";
  const start = css.indexOf(marker);
  const end = css.indexOf("/* EBook detail and podcast reading refinements.", start);
  assert.ok(start >= 0 && end > start);
  const rule = css.slice(start, end);
  assert.match(rule, /body\.ebooks-catalogue>\.jh-header\s*\{\s*position:\s*fixed!important/);
  assert.match(rule, /@media\(max-width:768px\)/);
  assert.match(rule, /body\.ebooks-catalogue #chips\s*\{[^}]*flex-wrap:\s*nowrap/);
  assert.match(rule, /body\.ebooks-catalogue #chips\s*\{[^}]*overflow-x:\s*auto/);
  assert.match(rule, /body\.ebooks-catalogue #chips>\.chip\s*\{\s*flex:\s*0 0 auto/);
  assert.doesNotMatch(rule, /display:\s*none|visibility:\s*hidden|(?:^|[;{])\s*(?:color|background(?:-color)?):/im);
});


test("catalogue header keeps the no-JS navigation available without expanding the mobile row", () => {
  const marker = "/* Prevent pre-boot desktop navigation";
  const start = css.indexOf(marker);
  assert.ok(start >= 0, "pre-boot mobile navigation rule required");
  const rule = css.slice(start);
  assert.match(rule, /@media\(max-width:768px\)/);
  assert.match(rule, /body\.ebooks-catalogue \.jh-nav-desktop\s*\{[^}]*position:absolute/);
  assert.match(rule, /max-height:calc\(100svh - 72px\)/);
  assert.match(rule, /overflow-y:auto/);
  assert.match(rule, /background:var\(--bg-dark\)/);
  assert.doesNotMatch(rule, /display:none|visibility:hidden|#[0-9a-fA-F]{3,8}\b/, "retain fallback navigation and brand palette");
});

test("R2 transcript navigation keeps accessible 44px touch targets", () => {
  assert.ok(
    css.includes(".transcript-nav>a{display:inline-flex;align-items:center;min-height:44px;padding:0 6px}"),
    "all R2 transcript navigation links must be 44px high"
  );
});

// Retain editorial discovery density on narrow screens without losing any navigation routes.
test("home intent navigation stays two columns below 440px", () => {
  assert.match(css, /\.home-intent nav\{display:grid;grid-template-columns:1fr 1fr\}/);
  assert.match(css, /@media \(max-width:440px\)\{\.home-trust-strip\{grid-template-columns:1fr\}\}/);
  assert.doesNotMatch(css, /@media \(max-width:440px\)\{[^}]*\.home-intent nav/);
  assert.match(css, /\.home-intent a\{[^}]*min-height:44px/);
});
