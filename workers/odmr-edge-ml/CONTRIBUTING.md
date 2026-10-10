# Contributing

Questions, bug reports and pull requests are all welcome. Issues are open and I answer them.

If you have a question, open an issue and say what you're trying to do. "How do I run this on my data?" is a fine question.

A bug report should include the command you ran, what you expected, what happened instead, the full error output and the commit hash.

Keep each pull request to a single change and add a test that fails without it. Run the tests before you open it.

```bash
cd workers/odmr-edge-ml
PYTHONPATH=src:../nv-sensor-sim/src python -m pytest -q
```

If you reuse part of this repository somewhere else, I'd like to know where and how. Open an issue for that too, since it's how I find out which parts are useful.

Contributions are accepted under the same terms as the repository; see the LICENSE file at the repository root.
