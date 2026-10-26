# FreeGame-info UI Refinement Implementation Plan

> For agentic workers: implement tasks in order and verify the rendered result before publishing the review branch.

**Goal:** Fix the existing website's presentation while retaining all data contracts.

**Architecture:** Shared inline CSS in epic-freebies.html.template; semantic hooks in render_html.py; same stylesheet embedded into history. Retain public rendering signatures, collectors, snapshots and database schema.

**Tech Stack:** Python standard library, static HTML/CSS, existing vanilla JavaScript.

- [x] Add regression cases in tests/test_render_ui.py for safely separated Epic metadata, inline shared history CSS, tab accessibility and unchanged snapshot/share payload. Run `python3 -m unittest discover -s tests -v` and confirm the relevant defects fail.
- [x] Replace duplicate utility rules/runtime CSS with scoped semantic styles in epic-freebies.html.template, retaining all placeholder names and advertisement configuration. Add classes in existing rendered card HTML; fix escaping of joined metadata without changing its values.
- [x] Embed the template style block in render_history_page, replace its blue theme shell with the same red/black layout, preserve all historic records and links.
- [x] Add keyboard tab behavior and avoid synchronous layout reads in every countdown tick. Honor share disabled state and preserve pre-generated download URLs.
- [x] Generate local pages from existing sample JSON for all platforms, historical records, missing images and long titles. Inspect desktop and narrow iframe layouts in the browser; check all tabs and keyboard focus.
- [x] Run unittest, compileall, extracted JavaScript syntax checks and git diff --check. Review the source diff for accidental changes to collectors, data, workflow, schema or share payload. Deliver via the review branch codex/refine-freegame-ui and an attached pull request.

## Verification results

- 12 rendering regression tests pass, including the production archive URL format.
- Browser checks: 320, 375, 759, 760, 1024 and 1440px iframe viewports; no horizontal overflow; platform buttons are 44px high. Additional 320px long-title and 375px empty/history fixtures pass.
- All six platform panels switch correctly; ArrowRight moves selected/focused tab together and leaves one active panel and one tab stop.
- The preview uses the unchanged public site snapshot (last synced 2026-10-04); ad scripts are excluded from localhost previews only. External provider overlays and stale data classification are outside this style-only change.
