---
name: web-interface-guidelines
description: "Review web UI code against Vercel's Web Interface Guidelines: accessibility, focus, forms, animation, typography, images, performance, navigation state, touch, theming, i18n, hydration and copy. Use when asked to review a UI, check accessibility or audit a page's UX, or before shipping a React or Next.js screen."
---

# Web Interface Guidelines

Review the files the user names (or ask which ones) against the rules in
[references/guidelines.md](references/guidelines.md), Vercel's Web Interface Guidelines, copied
here at a fixed commit so every review uses rules someone has read.

1. Read references/guidelines.md in full before reviewing.
2. Read each file to review. For a pattern (`src/**/*.tsx`), list the matches first.
3. Check every rule that applies to the file. Flag the anti-patterns the guidelines list.
4. Report in the guidelines' output format: grouped by file, one `file:line - issue` per finding,
   `✓ pass` for a clean file, no preamble. Explain only when the fix isn't obvious.

Some rules are house style rather than accessibility or correctness (Title Case for headings,
`…` and curly quotes, `&` over "and"). When the project's own style guide says otherwise, follow
the project and say so once.

The upstream skill fetched these rules from the guidelines repository's `main` branch at every
review. This copy doesn't: to take newer rules, compare with
https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md and update the copy
through a reviewed change.
