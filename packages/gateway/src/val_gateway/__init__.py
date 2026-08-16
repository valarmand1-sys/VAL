"""The Model Gateway (`01-architecture.md` §5.1).

All model inference enters here. No component calls a provider SDK directly.

**Why this is a package and not a service.** The gateway asks policy and calls
providers, and `providers` may never depend on `policy` (§3), so orchestration
needs a home that may depend on both. Putting it in `apps/api` and having the
worker reach it over HTTP would couple the worker's availability to the API
process and add a network hop and a failure mode to every model call — buying
"one place writes model_calls" at the price of two processes needing each other
alive. One write path is a property of one *implementation*, not one process.
So: a shared package, imported by both apps, each of which works independently.

Decided by Lord Armand, 15 August 2026.
"""

__all__: list[str] = []
