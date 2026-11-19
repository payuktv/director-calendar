"""Collect the common suite everywhere and native Shell tests only on Windows."""
import sys

import pytest


@pytest.fixture(scope='session', autouse=True)
def default_display_language():
    # Legacy UI assertions use Russian. Language tests supply other OS preferences explicitly.
    from director_control import i18n
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(i18n, 'system_language', lambda: 'ru-RU')
        yield

# The real .lnk/pythonw integration is required by Windows CI. It has no
# Linux equivalent, so it is outside that platform's suite rather than skipped.
collect_ignore = ['windows'] if sys.platform != 'win32' else []
