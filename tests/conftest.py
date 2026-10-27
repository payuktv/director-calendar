"""Collect the common suite everywhere and native Shell tests only on Windows."""
import sys

# The real .lnk/pythonw integration is required by Windows CI. It has no
# Linux equivalent, so it is outside that platform's suite rather than skipped.
collect_ignore = ['windows'] if sys.platform != 'win32' else []
