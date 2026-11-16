---
name: stagehand-browse
description: Drive a local or self-hosted Chrome from the shell with Stagehand's browse CLI: open pages, accessibility snapshots, clicks, forms, screenshots, network capture. Use in a repository with the stagehand pack to browse, inspect or check a web page.
license: MIT
compatibility: "The browse CLI (setup-machine.sh installs the pinned version) and Chrome or Chromium on the machine, or a Chrome reached over CDP. No Browserbase account."
allowed-tools: Bash
---

# Stagehand's browse CLI, self-hosted

`browse` drives a browser through a background daemon. Here it always drives a **local** Chrome
or one you host and reach over **CDP**. It needs no model and no account: you read the page and
choose each action.

## Setup check

```bash
browse --version && browse doctor
```

If `browse` is missing, report that `setup-machine.sh` installs it at the pinned version; this
template pins it, so install it no other way. `browse <topic> --help` gives the exact flags for
any command.

## Pick the browser on the first command

The first browser command of a session sets its mode; a running session keeps it.

```bash
browse open https://example.com --local              # headless Chrome on this machine
browse open https://example.com --local --headed     # the same, visible
browse open https://example.com --cdp 9222           # a Chrome you run with a debugging port
browse open https://example.com --cdp ws://chrome.internal:9222/devtools/browser/<id>
```

- **--local** is the default choice: development, localhost and trusted sites.
- **--cdp** attaches to a Chrome you host, such as a browser container on your own network.
- **--auto-connect** attaches to the user's own running Chrome, with their logins and cookies:
  use it only when the user asks for exactly that.

Pass `--local` or `--cdp` on every first command. A `BROWSERBASE_API_KEY` in the environment
would make `browse` default to Browserbase's cloud, which this template doesn't use.

## Work in named sessions

Give each task its own session; commands without one share `default` and overwrite each other's
page. If `BROWSE_SESSION` is already set, every command targets it: pass no `--session`.

```bash
browse open http://localhost:3000 --session checkout --local
browse snapshot --session checkout
browse stop --session checkout
```

## The loop: open, snapshot, act, snapshot

```bash
browse open http://localhost:3000 --local
browse snapshot                 # accessibility tree with refs like @0-5
browse click @0-5
browse fill @0-8 "search text"
browse snapshot                 # confirm, and get fresh refs
browse stop
```

Refs change after every navigation, click, submit or re-render: snapshot again before using
another one. Prefer `snapshot` over screenshots; take a screenshot when layout, images or
pixels matter.

## Commands

Navigation and waiting:

```bash
browse open <url>
browse reload
browse back
browse forward
browse wait load
browse wait selector "#result"
```

Page state:

```bash
browse snapshot                      # the tree; --full adds the ref maps
browse get url
browse get title
browse get text body
browse get html "#main"
browse get markdown body
browse get value "#email"
browse eval "document.title"         # JavaScript in the page
browse screenshot --path page.png    # prints { "saved": "<path>" }
```

Interaction:

```bash
browse click @0-5
browse fill @0-8 "query"             # --press-enter submits
browse type "text for the focused element"
browse press Enter
browse select "select[name=country]" "Canada"
browse upload @0-12 ./file.pdf
browse highlight @0-5
browse is visible "#modal"
```

Mouse and viewport:

```bash
browse mouse click 240 320
browse mouse drag 80 80 310 100
browse mouse scroll 500 300 0 600
browse viewport 1280 720
```

Tabs, network and CDP events:

```bash
browse tab list
browse tab new http://localhost:3000/other
browse tab switch <target-id>
browse tab close <target-id>         # refuses to close the last tab
browse network on                    # capture requests; `network path` shows where
browse network off
browse cdp 9222 --domain Network     # stream raw CDP events as NDJSON
```

Sessions:

```bash
browse status
browse doctor --json
browse stop                          # idempotent: { "stopped": false } is success
browse stop --force
```

## When something fails

- **The same command fails twice**: stop repeating it. Run `browse doctor --json`, then change
  something: switch between `--local` and `--cdp`, or `browse stop --force` and start again.
- **No Chrome or Chromium found**: install Chrome, set the session to `--cdp` against a browser
  you host, or report what is missing.
- **No active page**: `browse status --session <name>`, then `browse open <url> --session <name>`.
- **An action misses**: snapshot and use a ref from the current tree.
- **401 Unauthorized**: `BROWSERBASE_API_KEY` is set and `browse` tried the cloud. Pass
  `--local`, or unset the variable.

## Source

Adapted from the `browse` skill in browserbase/stagehand (`packages/cli/skills/browse` at
`browse@0.11.3`, MIT, Copyright (c) 2024 Browserbase Inc.), keeping the local and CDP parts.
