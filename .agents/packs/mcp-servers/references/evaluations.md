# Evaluation questions for an MCP server

A server is good when a model that has nothing but its tools, and no other context, can answer
realistic questions with them. Unit tests cannot show that; a set of question and answer pairs
run through an agent can. The method follows the evaluation guide in Anthropic's `mcp-builder`
skill (Apache-2.0,
<https://github.com/anthropics/skills/blob/main/skills/mcp-builder/reference/evaluation.md>).
Use its criteria, not its harness: `scripts/connections.py` imports `streamablehttp_client`,
which mcp 2.x removed, and `scripts/requirements.txt` asks for an unpinned `mcp>=1.1.0`, which
now resolves to 2.x.

## Write the pairs

1. Read the tool list the way a model will: names, descriptions and schemas only
   (`fastmcp list <path to server.py>`, or the Inspector's `tools/list`).
2. Explore the data read-only yourself, through the in-memory client or the Inspector, and note
   facts that take several calls to reach.
3. Write about ten questions. Each one is:
   - **read-only and independent**: answering it changes nothing, and it needs no other
     question's answer;
   - **stable**: the answer will not drift (an order's ship date, not a count of open orders);
   - **multi-hop**: several tool calls, ideally across tools, with paging or filtering where the
     real data needs it;
   - **paraphrased**: worded with synonyms rather than the exact strings a keyword search would
     match;
   - **single-valued**: one answer you can check by string comparison, with its format stated
     in the question ("Answer with the ISO date", "Answer with the order id").
4. Answer every question yourself by calling the tools, and record the tool path you took. A
   question you cannot answer with the tools is a finding about the server, not a bad question.

Keep the file next to the tests, for example `evals/questions.xml`:

```xml
<evaluation>
  <qa_pair>
    <question>Which order placed in March 2026 by the customer with the most orders that month
      was the last to ship? Answer with the order id.</question>
    <answer>A-1042</answer>
  </qa_pair>
</evaluation>
```

The data behind the answers is fixture data: seed the server from a fixed file or database
snapshot, never from live systems, so the answers stay true and no question touches real
records.

## Run them

Start the server on loopback, then give an agent this server and nothing else. With Claude Code
(flags checked on 2.1.276), save this as `evals/mcp.json`:

```json
{"mcpServers": {"orders": {"type": "http", "url": "http://127.0.0.1:8000/mcp"}}}
```

```bash
cfg="$PWD/evals/mcp.json"
(cd "$(mktemp -d)" && claude -p "<question> Reply with the answer only." \
  --mcp-config "$cfg" --strict-mcp-config \
  --tools "" --allowedTools "mcp__orders__*" \
  --output-format json) | jq -r '.result'
```

- The empty directory keeps the project's `CLAUDE.md` and settings out of the agent's context.
- `--strict-mcp-config` loads only the servers in `--mcp-config`.
- `--tools ""` removes the built-in tools, so the agent cannot read the source or the database
  directly; it does not remove MCP tools.
- `--allowedTools "mcp__orders__*"` lets the server's tools run without a permission prompt.
- An entry with a `url` needs `"type": "http"`; without one Claude Code reads it as stdio and
  skips it.

Score by exact match after trimming whitespace. For each miss, read the transcript
(`--output-format stream-json --verbose`; `-p` refuses `stream-json` without `--verbose`) and
find the tool name, description, parameter or oversized result that misled the model. Fix the
server, keep the question, and rerun the set; a rising pass rate across server changes is the
signal.
