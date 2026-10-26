# FreeGame-info UI refinement

Approved in chat on 2026-10-26: retain the red/black identity, shorten the opening, unify cards and history, improve responsive layouts and keyboard focus. JSON, SQLite, collectors and deployment contracts stay unchanged.

Use one inline, self-contained stylesheet in the main template, reused by history rendering. Give card markup semantic classes without changing its data mapping. Keep original game names, descriptions, links, prices, platform membership and share payload. Preserve ad providers and identifiers, but place fixed in-content slots after navigation so the site's controls stay findable. Provider-injected floating overlays remain an external limitation.

Home: compact top bar and title, visible platform controls, consistent cover geometry, readable metadata, aligned actions. History: same palette and cards, dated sections and return navigation. Mobile: fluid gutters, no rotated content spilling outside the viewport, wrapping long words, stacked card actions and large touch targets. Keyboard: focus-visible styles, linked tabs/panels, arrow/Home/End traversal. Reduced motion: pause decorative movement without hiding information.

Verification: unittest regression coverage for HTML escaping, existing old/new snapshots, payload preservation, empty states, tab relationships, inline history CSS and share links; Python/JavaScript syntax checks; browser inspection of desktop and actual narrow iframe viewports. No live fetches or database writes needed for local preview. Submit changes in a reviewable branch/PR; do not deploy or merge.

## Style correction approved by user feedback

The original visual identity is binding: exact #d10000 red, black/white surfaces, dot texture, heavy italic typography, thick white borders, skewed tabs/actions, hard offset shadows, rotated GET badges and the bottom marquee. Restore these details and the single-column horizontal desktop card composition. Responsive fixes must contain the original decorative geometry rather than remove it. Keep the existing data, rendering fixes, keyboard access and sharing behavior.
