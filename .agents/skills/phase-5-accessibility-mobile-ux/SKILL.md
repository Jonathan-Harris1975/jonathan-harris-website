# Phase 5C Accessibility + Mobile UX Gate

This skill wires the `accessibility-audit` workflow into the rendered Mobile UX hard-gate audit.

## Scope

- WCAG 2.2 AA, with WCAG 2.1 AA compatibility notes.
- Legal mapping: ADA, EAA, Section 508 and AODA.
- Rendered evidence from the same Playwright/mobile viewport pass used by the Mobile UX audit.

## Fail-closed policy

The accessibility lane is report-first. It may block/report accessibility defects automatically, but remediation remains PR-gated unless a future safe-fix rule explicitly allows it.

## Checks

- Page language and title.
- Visible image alt decisions.
- Accessible names for buttons/links/controls.
- Form labels.
- Meaningful link text.
- Heading structure.
- Keyboard/focus guidance in the report.
