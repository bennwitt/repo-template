# One-way doors

A **one-way door** is a decision that is expensive or impossible to reverse once others build
on it; a **two-way door** can be walked back in an afternoon. Settle the first kind now, with a
reason; give the second kind the boring default and move on. The sort is the whole point of the
plan: time spent deciding two-way doors is the waste the 72% plan removes.

## Usually one-way

| Decision | Why it is hard to reverse |
| --- | --- |
| Language and runtime | Every file, test and tool chain depends on it |
| Kind of data store (relational, document, files, queue) | Changes the shape of every query and the reload path |
| Hosting shape (one box, container, serverless, managed platform) | Changes packaging, secrets, networking and cost |
| Public interface or contract (API shape, file format, event schema) | Others build on it; versioning begins the day it ships |
| Identifiers and keys | Spread through every table, URL and log |
| Authentication boundary (who is trusted, where) | Retrofitting trust boundaries touches everything |
| Tenancy (one tenant or many) | Multi-tenant later means a new key in every table |
| The one innovation token | The team's unfamiliarity is the cost, and it compounds |

## Usually two-way

| Decision | Boring default |
| --- | --- |
| Web or CLI framework within the chosen language | What the team already uses |
| ORM or raw queries | Whichever the team reads faster |
| Internal module layout | Flat until a second feature needs a seam |
| Caching | None until a measurement asks for it |
| Background jobs | A loop or a cron entry until volume asks for a queue |
| Configuration format | Environment variables until the second environment appears |
| Logging and metrics | Structured logs to stdout; dashboards when someone reads them |
| Retries and timeouts | One timeout per outbound call; retries when a dependency proves flaky |

## The test

Ask "if this is wrong, what does undoing it cost?" A one-way door answers in weeks of work
or in data nobody can recover. A two-way door answers in a pull request. When unsure, treat it
as two-way, take the boring default, and write one line saying so; that line is the whole
record the hardening path needs.
