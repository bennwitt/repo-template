# Code Connect

Code Connect links each component in the Moore Design System library to its component in code.
Dev Mode then shows the real snippet, and the `figma` server returns it from
`get_design_context` and `get_code_connect_map`.

## Requirements

- A Dev or Full seat. Professional allows one active library and one framework: the Moore Design
  System and React.
- Components published from the Prod library; an unpublished component can't be mapped.
- Node 18 or later.
- A personal access token with **Code Connect: Write** and **File content: Read**, in
  `FIGMA_TOKEN`. Figma tokens last 90 days at most; make a new one in Figma's settings when it
  expires.

## Set up the repository

1. Add the CLI as a dev dependency at the newest release at least 7 days old.
   `npm view @figma/code-connect time --json` lists release dates; then
   `npm install --save-dev @figma/code-connect@<version>`.
2. Add `figma.config.json` at the repository root:

   ```json
   {
     "codeConnect": {
       "include": ["src/**/*.figma.ts"],
       "label": "React",
       "language": "jsx"
     }
   }
   ```

   With TypeScript, add `"@figma/code-connect/figma-types"` to `compilerOptions.types` in
   `tsconfig.json`.

## Map a component

Write a **template file** beside the component, named after it (`Button.figma.ts`).
`npx figma connect create <component url>` writes a starting point. Template files are the
maintained way; the React parser (`figma.connect(...)` files) is legacy.

```ts
// url=https://www.figma.com/design/<fileKey>/Moore-Design-System?node-id=123-456
import figma from 'figma'

const instance = figma.selectedInstance
const label = instance.getString('Label')
const disabled = instance.getBoolean('Disabled')
const size = instance.getEnum('Size', { Large: 'lg', Medium: 'md', Small: 'sm' })

export default {
  example: figma.code`<Button size={${size}} disabled={${disabled}}>${label}</Button>`,
  imports: ['import { Button } from "@/components/ui/button"'],
}
```

The `url` is the library component's link (right-click it, **Copy link to selection**); the
property names are the component's properties in Figma. Code Connect reads template files as
strings and never runs them, so a conditional appears in the snippet verbatim.

## Publish

```bash
FIGMA_ACCESS_TOKEN="$FIGMA_TOKEN" npx figma connect publish --dry-run   # check first
FIGMA_ACCESS_TOKEN="$FIGMA_TOKEN" npx figma connect publish
```

Pass the token through `FIGMA_ACCESS_TOKEN`, never `--token`, which leaves it in shell history
and the process list. `npx figma connect preview` shows how snippets will look in Dev Mode;
`npx figma connect unpublish` removes mappings. Publish again whenever a mapped component's
properties change.

## Mappings from an agent

`add_code_connect_map` and `send_code_connect_mappings` save mappings straight from the agent;
they are write tools, on `figma-write` only. When Figma's own plugin is installed, its
`figma-code-connect` skill writes template files in bulk. Without either, write template files
as above and publish them with the CLI.
