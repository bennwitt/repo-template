---
name: data-structure-selector
description: "Choose a data structure from the operations the code needs (lookups, ordered scans, inserts and deletes, priority, prefix or range queries) and their complexity, against the language's standard types. Use when picking or replacing a collection, map, tree, heap or trie, or when complexity-analyzer finds the structure is the bottleneck."
allowed-tools:
  - Read
  - Write
  - Grep
  - Glob
graph:
  domains: [domain:computer-science]
  specializations: [specialization:algorithms-optimization]
  skillAreas: [skill-area:dynamic-programming, skill-area:graph-algorithms]
  roles: [role:backend-engineer, role:computational-scientist]
# Changed by repo-template (https://github.com/bennwitt/repo-template): description. Original: https://github.com/a5c-ai/babysitter/tree/feb68abe397acc14f32b34984975c48fedba2b33/library/specializations/algorithms-optimization/skills/data-structure-selector (MIT).
---

# Data Structure Selector Skill

## Purpose

Select the optimal data structure based on required operations, their frequencies, and time/space constraints.

## Capabilities

- Analyze required operations (insert, delete, query, update)
- Match to optimal data structure
- Consider time/space trade-offs
- Suggest augmentations for custom requirements
- Compare alternatives with complexity analysis

## Target Processes

- data-structure-implementation
- algorithm-implementation
- complexity-optimization

## Selection Framework

### Operation Analysis
1. What operations are needed?
2. What are the frequency/priority of each operation?
3. What are the constraints (N, Q, time limit)?
4. Is persistence needed?
5. Are range operations required?

### Common Selection Patterns

| Operations | Best Choice |
|------------|-------------|
| Insert, Delete, Search | BST / Hash Map |
| Range sum, Point update | Fenwick Tree |
| Range query, Range update | Segment Tree + Lazy |
| Union, Find | DSU |
| Min/Max with add/remove | Multiset / Heap |
| Predecessor/Successor | Ordered Set / BST |

## Input Schema

```json
{
  "type": "object",
  "properties": {
    "operations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "frequency": { "type": "string" },
          "constraints": { "type": "string" }
        }
      }
    },
    "constraints": { "type": "object" },
    "preferences": { "type": "array" }
  },
  "required": ["operations"]
}
```

## Output Schema

```json
{
  "type": "object",
  "properties": {
    "success": { "type": "boolean" },
    "recommended": { "type": "string" },
    "complexities": { "type": "object" },
    "alternatives": { "type": "array" },
    "augmentations": { "type": "array" },
    "reasoning": { "type": "string" }
  },
  "required": ["success", "recommended"]
}
```
