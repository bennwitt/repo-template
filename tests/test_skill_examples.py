"""Execute the adopted HTTP instrumentation examples with controlled request fixtures."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="example execution needs Node.js")
@pytest.mark.parametrize("reference", [False, True])
def test_http_metric_examples_keep_dynamic_ids_out_of_labels(reference: bool) -> None:
    folder = ROOT / ".agents/packs/monitoring-expert"
    path = folder / ("references/prometheus-metrics.md" if reference else "SKILL.md")
    blocks = re.findall(r"```(?:js|typescript)\n(.*?)\n```", path.read_text(), re.DOTALL)
    metrics = next(block for block in blocks if "new Counter" in block)
    if reference:
        metrics += "\n" + next(block for block in blocks if "function instrumentRoute" in block)
    metrics = re.sub(r"^import .*;$", "", metrics, flags=re.MULTILINE)
    harness = """
const assert = require('node:assert/strict');
const counters = [], durations = [], routes = [];
class Registry {}
class Counter {
  constructor(options) { this.options = options; }
  inc(labels) { counters.push(labels); }
}
class Histogram {
  constructor(options) { this.options = options; }
  startTimer(initial) { return final => durations.push({ ...initial, ...final }); }
}
class Gauge {}
class Summary {}
const handleOrder = () => {};
const app = { get: (...args) => routes.push(args) };
"""
    assertions = """
const route = routes.find(args => args[0] === '/orders/:id');
assert.ok(route, 'example must install instrumentation on a configured route');
for (let id = 0; id < 100; id++) {
  let finish, nextCalled = false;
  const req = { method: 'GET', path: '/orders/' + id };
  const res = { statusCode: 200, on: (event, callback) => { finish = callback; } };
  route[1](req, res, () => { nextCalled = true; });
  assert.equal(nextCalled, true);
  finish();
}
assert.equal(counters.length, 100);
assert.equal(durations.length, 100);
assert.equal(new Set(counters.map(x => JSON.stringify(x))).size, 1);
for (let i = 0; i < counters.length; i++) {
  const counter = counters[i], duration = durations[i];
  assert.equal(counter.route ?? counter.path, '/orders/:id');
  assert.equal(duration.route ?? duration.path, '/orders/:id');
  assert.equal(counter.method, duration.method);
}
"""
    done = subprocess.run(
        ["node", "-e", harness + metrics + assertions], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
