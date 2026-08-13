"""A deliberate dependency-direction violation, for proving CI rejects it.

`packages/policy` may depend on `packages/domain` and nothing else
(01-architecture.md §3). This file reaches into `apps/desktop`, which is the
exact violation WP-0.1 requires CI to reject.

This file is not part of the build and is removed once CI has failed on it.
"""

import sys

sys.path.insert(0, "../../apps/desktop/src")
