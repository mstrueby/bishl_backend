#!/bin/bash
set -e

PYTHON=/home/runner/workspace/.pythonlibs/bin/python3.12

# The platform pip.conf has an invalid use-feature flag that causes pip to exit
# with code 3 even when the install succeeds. Allow 0 (clean) and 3 (config
# warning) but still propagate any other non-zero exit code (real failures).
set +e
$PYTHON -m pip install -r requirements.txt --quiet
pip_exit=$?
set -e
if [ $pip_exit -ne 0 ] && [ $pip_exit -ne 3 ]; then
    exit $pip_exit
fi

# Ensure pytest launcher uses Python 3.12 (pip installs it with #!/usr/bin/env python3
# which resolves to the system Python 3.11 in this environment).
PYTEST_BIN=/home/runner/workspace/.pythonlibs/bin/pytest
if [ -f "$PYTEST_BIN" ]; then
    sed -i '1s|.*|#!'"$PYTHON"'|' "$PYTEST_BIN"
fi
