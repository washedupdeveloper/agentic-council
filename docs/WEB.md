# The runtime lane

Every other probe in `scripts/probes.py` reads the source. `browser` is the only one that loads the
artifact and reports what happened, because that is the only way to answer what a frontend change
actually turns on: hydration that throws, a route that 404s, a selector that exists in a mock and
not in the DOM.

Reviewing that by reading produces a confident wrong answer. So the lane's contract is: **an
observation, or a stated absence.**

## Run it

```bash
council probes browser --repo .                         # static entry point, file:// URL
COUNCIL_WEB_URL=http://127.0.0.1:3000 council probes browser --repo .   # a server you started
COUNCIL_BROWSER_CMD='nix run nixpkgs#chromium --' council probes browser --repo .
```

| Variable | Meaning |
|---|---|
| `COUNCIL_BROWSER_CMD` | The driver command, split like a shell argv. Defaults to the first of `chromium`, `chromium-browser`, `google-chrome`, `google-chrome-stable`, `chrome` on `PATH`. |
| `COUNCIL_WEB_URL` | Load this URL instead of a static entry. Use it for an SPA that needs a dev server, or for a service whose HTTP surface is the thing under review. |

The entry-point order is `index.html`, `public/index.html`, `dist/index.html`, `build/index.html`,
`site/index.html`. A repository with none of those and no `COUNCIL_WEB_URL` is **not in the lane**:
the probe reports `ran: false`, which is why a JavaScript library is never scored on a page it does
not have.

## What it observes

The probe runs the driver with one argv contract (`probes.browser_argv`):

```
<driver> --headless=new --disable-gpu --no-sandbox --hide-scrollbars --disable-dev-shm-usage
         --virtual-time-budget=8000 --screenshot=<png> --dump-dom <url>
```

| Signal | Severity | Why it is a finding |
|---|---|---|
| non-zero exit, or no DOM at all | critical | the page did not load |
| no visible text **and** no media element | critical | the app did not mount — the classic failed hydration |
| `Uncaught`, `TypeError`, `ReferenceError`, `SyntaxError`, `RangeError`, `Failed to load resource` on stderr | major | the page threw after load |
| an asserted selector absent from the rendered DOM | major | the feature the reviewer claims exists is not there |
| `web-assertions.json` does not parse | minor | the repository's own assertions could not be read |

`signal = 100 − 40·critical − 20·major − 5·minor`, floored at 0. Two failing findings is 40, so a
page that throws twice cannot pass on other signals.

## Assertions a repository can declare

`.review-council/web-assertions.json` — optional, and checked only when the page rendered:

```json
{
  "assertions": [
    {"selector": "#app", "why": "the root node must exist"},
    {"selector": ".dashboard", "why": "the dashboard must render"},
    {"selector": "text:Sign in", "why": "the auth boundary must be visible"},
    {"selector": "form[action=/login]", "why": "the form must post to the login route"}
  ]
}
```

The selector grammar is deliberately small: `#id`, `.class`, `tag`, `tag[attr=value]` and
`text:<phrase>`. That is not a CSS engine and does not pretend to be one — a full matcher is a
dependency, and an unsupported selector would otherwise pass silently as "absent", which is the
worse failure. A repository that needs more should assert with `text:` on the rendered content.

## Artifacts

The DOM dump and the screenshot are written to a fresh temporary directory
(`council-browser-*`), never into the repository under review: a review is a read, and the probe's
own test asserts the tree is byte-identical afterwards. Both paths are in the probe's `note`, and
every finding's `falsifiable_check` carries the exact command, so the claim can be re-run by hand.

## What it does not do

- **No interaction.** It loads and renders; it does not click, type, or navigate client-side
  routes. A change that only breaks after a click needs `COUNCIL_WEB_URL` plus the reviewer's own
  steps, and the rubric requires the finding to say so rather than guess.
- **No console API.** Console output is read from the browser's stderr, not from CDP. That catches
  uncaught errors, not `console.error` a page raised and caught itself.
- **No driver shipped.** Chromium is a large closure and the council image is a review tool, not a
  browser. `council doctor` reports whether a driver resolves; when none does, the lane reports
  `ran: false`, beta drops, and the report says the runtime was not observed.