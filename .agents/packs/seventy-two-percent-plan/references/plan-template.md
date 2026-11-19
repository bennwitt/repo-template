# Plan template

One page. Replace every bracket; delete nothing else. A section with nothing to say gets the
word "none" so the reader knows it was considered.

```markdown
# <name>: 72% plan

**Problem.** <one sentence: what is wrong or missing today>
**Use case.** <the one case this serves, and who uses it>
**Appetite.** <N days or weeks>, fixed. Scope bends; the date does not.

## Non-goals
- <what this will not do>
- <...>
- <...>

## One-way doors (settled)
| Decision | Choice | Why |
| --- | --- | --- |
| <runtime / language> | <choice> | <reason, including "the team already runs it"> |
| <data store kind> | <choice> | <...> |
| <hosting shape> | <choice> | <...> |
| <public interface or contract> | <choice> | <...> |
| <identifiers or keys> | <choice> | <...> |

Innovation token: <the one new technology, or none>.

## Two-way doors (boring default, reversible)
- <decision>: <default>
- <...>

## Data
Disposable: <stores>, rebuilt by `<reload command>`.
Precious: <none, or the exact tables/files and why>.

## Reliability
Downtime tolerance: <plain words>. Recovery: restart.
Handled: bad input, <dependency> down, restart mid-work. Everything else errors with context.

## Walking skeleton
<the thinnest end-to-end path, through every one-way door, running in the target environment>
Due: <within the first quarter of the appetite>.

## Deliberately skipped
| Not built | Add when |
| --- | --- |
| <feature> | <trigger> |
| <...> | <...> |

## Rabbit holes
- <known risk>: <the line or two that keeps it shallow>

## Shortcuts taken
| Shortcut | Interest | Pay when |
| --- | --- | --- |
| <the deliberate corner cut> | <low: rarely touched / high: on the hot path> | <trigger> |

## Hardening path
<three to five lines: what a larger team would change first, which skipped items come first,
what becomes precious data>

## Left to the builder
<the two-way doors and details this plan does not decide>

Planned <date>. Rerun the 72% plan on a pivot; do not patch this one.
```
