# Principles behind the 72% plan

Each step of the plan leans on a named idea. The source says what its author prescribes, not
that it is proven; the plan uses each where it earns its place. Sources were read on
2026-11-19.

## Appetite: fixed time, variable scope

Shape Up (Basecamp) starts a project from a time budget, the **appetite**, and designs down to
it: "Estimates start with a design and end with a number. Appetites start with a number and end
with a design." The principle is named "fixed time, variable scope", and stating the appetite in
the pitch "prevents unproductive conversations" about expanding scope. Its two standard sizes
are a small batch (one or two weeks) and a big batch (six weeks).
Steps 3 and 11 come from here.
Source: [Shape Up, chapter 3](https://basecamp.com/shapeup/1.2-chapter-03).

## The pitch: problem, appetite, solution, rabbit holes, no-gos

Shape Up's pitch always carries five ingredients. **No-gos** are "functionality or use cases we
intentionally aren't covering to fit the appetite or make the problem tractable"; a **rabbit
hole** is a known risk, and "sometimes addressing a rabbit hole just requires a few lines of
text." The plan's non-goals, rabbit holes and deliberately-skipped list are these ingredients;
"one page" is this skill's bound, not Shape Up's.
Source: [Shape Up, chapter 6](https://basecamp.com/shapeup/1.5-chapter-06).

## One-way and two-way doors

Bezos's 2015 letter: "Some decisions are consequential and irreversible or nearly irreversible,
one-way doors, and these decisions must be made methodically, carefully, slowly." The 2016
letter: "never use a one-size-fits-all decision-making process. Many decisions are reversible,
two-way doors. Those decisions can use a light-weight process." Heavy process on two-way doors
breeds slowness; light process on one-way doors is how small companies go extinct. The plan's
door sort (step 4) is this rule, with one caution from practice: reversibility decays as code
entangles, so the sort records reversal cost, not a permanent label.
Sources: [2015 letter (SEC exhibit)](https://www.sec.gov/Archives/edgar/data/1018724/000119312516530910/d168744dex991.htm),
[2016 letter](https://www.aboutamazon.com/news/company-news/2016-letter-to-shareholders).

## Decide at about 70% of the information

The same 2016 letter: "most decisions should probably be made with somewhere around 70% of the
information you wish you had. If you wait for 90%, in most cases, you're probably being slow,"
paired with being "good at quickly recognizing and correcting bad decisions." This is a rule
about decision speed, not software design; the plan borrows it as the stop rule (step 11) and
the pivot rule (rerun the plan, do not patch it). The 72 in the name is this number with a
little extra care for the one-way doors.
Source: [2016 letter](https://www.aboutamazon.com/news/company-news/2016-letter-to-shareholders).

## Prudent debt, not reckless debt

Fowler's technical-debt quadrant: "the useful distinction isn't between debt or non-debt, but
between prudent and reckless debt." A considered shortcut taken to ship is prudent, and "may
not be worth paying down if the interest payments are sufficiently small, such as if it were in
a rarely touched part of the code-base." Going quick-and-dirty on purpose "is usually a reckless
debt, because people underestimate where the DesignPayoffLine is": good design exists to make
you faster within weeks, not years. The shortcuts table in the plan is a prudent-debt register:
each shortcut named, its interest estimated, its payoff trigger written down.
Sources: [TechnicalDebtQuadrant](https://martinfowler.com/bliki/TechnicalDebtQuadrant.html),
[DesignPayoffLine](https://martinfowler.com/bliki/DesignPayoffLine.html).

## Sacrificial architecture

Fowler: the right call for an early system can be one you plan to throw away once it has done
its job, because what you learn building it is worth more than the code. The plan's hardening
path (step 10) is the written form of that intent: which parts a larger team replaces first,
and what becomes precious when they do.
Source: [SacrificialArchitecture](https://martinfowler.com/bliki/SacrificialArchitecture.html).

## YAGNI

Fowler's YAGNI: building a presumptive feature costs the cost of building it, the cost of
delaying the feature you need now, the cost of carrying it, and the cost of repairing it when
the presumption turns out wrong; only the first is visible. Kent Beck's later note is that the
rule was never about saving typing but about keeping options open until the information
arrives. The plan's "two concrete callers before an abstraction" and "add when the second value
appears" rules are YAGNI applied to structure rather than features.
Sources: [Yagni](https://martinfowler.com/bliki/Yagni.html),
[Kent Beck, "The cost YAGNI was never about"](https://newsletter.kentbeck.com/p/the-cost-yagni-was-never-about).

## Choose boring technology

McKinley's essay: a company gets about three **innovation tokens**; spend them on the problem
that is the business, and run the rest on technology whose failure modes are known. Every new
component adds operational surface for the whole team. The plan allows one token per project
(step 5) and names it, so the choice is a decision rather than a drift.
Source: [Choose Boring Technology](https://mcfunley.com/choose-boring-technology).

## Gall's law and the walking skeleton

Gall, *Systemantics* (1975): "A complex system that works is invariably found to have evolved
from a simple system that worked." Cockburn's **walking skeleton** is the engineering form: a
tiny implementation that performs a small end-to-end function through the real architecture,
then grows. The Pragmatic Programmer's **tracer bullets** are the same move under another name,
with the emphasis that the skeleton is kept, not thrown away. Step 8 is this.
Sources: [Systemantics](https://en.wikipedia.org/wiki/Systemantics); Cockburn, *Crystal Clear*
(2004), "Walking Skeleton"; Hunt and Thomas, *The Pragmatic Programmer* (1999; 20th anniversary
edition 2019), "Tracer Bullets".

## The prototype pitfall

Atwood: a prototype that ships becomes the product, with its shortcuts and none of its
intent. The plan keeps the 72% solution distinct from a throwaway (the `prototype` skill is for
throwaways) by giving it tests on the skeleton and the one-way doors, a reload command, and a
written list of what was skipped.
Source: [The Prototype Pitfall](https://blog.codinghorror.com/the-prototype-pitfall/).

## Disposable data

This is the plan's own rule rather than a cited one: when every store can be rebuilt from its
source by a command that exists, a schema change is a two-way door, and the migration framework,
backups and versioned schemas that precious data needs are deliberately skipped until precious
data appears. The reload command is the proof; without it the data is precious whether anyone
admits it or not.

## Lean decision records

MADR 4.0.0 (MIT OR CC0-1.0) is "a lean way" to capture decisions: only context and problem
statement, considered options and decision outcome are required. The plan's one-way-door table
is leaner still, one row per door, and the hardening path says when a larger team should
promote those rows to records with the `domain-modeling` skill.
Source: [MADR](https://adr.github.io/madr/).
