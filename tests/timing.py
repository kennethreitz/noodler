"""Wall-clock budgets assume an idle machine.

A loaded computer — a browser, a build, this suite itself — stretches a
callback without the callback having started to do more work. The strict
budget still applies when the machine is quiet. Under load, the check only
fails if the work has clearly stopped being realtime.
"""

import os


def machine_is_quiet(limit: float = 2.0) -> bool:
    try:
        return os.getloadavg()[0] < limit
    except OSError:
        return True
