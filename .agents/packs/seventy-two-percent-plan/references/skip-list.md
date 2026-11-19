# Deliberately skipped

The features an enterprise system needs and a 72% solution does not build until a trigger
fires. Copy the rows that apply into the plan, with the trigger made specific. "Skipped" means
considered and declined, with the moment to revisit written down; it never means forgotten.

| Not built | Add when |
| --- | --- |
| High availability, failover, multi-region | Downtime tolerance in the plan is no longer true |
| Horizontal scaling, load balancing | One box is measured past its limit, not predicted to be |
| Multi-tenancy | A second tenant is signed, not imagined |
| Roles and permissions beyond "signed in" | A second kind of user exists with different rights |
| Audit log | Someone is required to answer "who changed this" |
| Internationalization | A user who needs a second language exists |
| Schema migrations framework | Precious data appears that cannot be reloaded |
| Backups and restore drills | Same trigger: precious data |
| Rate limiting and quotas | A caller has hurt the service once |
| Plugin points, hooks, extension APIs | A second implementation needs the same seam |
| Configuration UI | The second person who is not the author needs to change settings |
| Feature flags | Two variants must run at once for real users |
| Caching layers | A measurement shows the hot path, not a guess |
| Message queue or event bus | A loop or cron entry is measured too slow, or work must survive a restart |
| Microservices | Two teams need to deploy independently |
| Observability platform | Logs to stdout no longer answer the questions being asked |
| Secrets manager | Environment variables cannot meet a rotation or audit need |
| Formal SLOs and on-call | Someone else depends on uptime and says so |
| Performance past the stated load | The stated load is reached |
| Exotic or in-house replacements for standard tools | Never, in a 72% plan: it is the innovation token or it waits |
