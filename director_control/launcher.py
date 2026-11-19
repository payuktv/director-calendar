"""GUI entry point with a visible error if startup fails without a console."""
import sys

from .i18n import select_language, tr
from .desktop import show_message
from . import diagnostics


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--verify-installation':
            from .distribution_check import verify_installation
            return verify_installation(sys.argv[2])
        select_language('auto')
        diagnostics.configure()
        diagnostics.install_hooks()
        from .windows_lifecycle import hold_installer_mutex
        hold_installer_mutex()
        from . import __version__
        from .package_update import launch_ready, packaged
        if packaged():
            try:
                if launch_ready(sys.executable, __version__) is not None:
                    return 0
            except OSError as exc:
                diagnostics.record_error('startup', exc)
                show_message(tr('Не удалось запустить подготовленное обновление. Открываем текущую версию.'), error=True)
        from .ui import run_app
        return run_app()
    except Exception as exc:
        if len(sys.argv) == 3 and sys.argv[1] == '--verify-installation':
            import json
            from pathlib import Path
            Path(sys.argv[2]).write_text(json.dumps({'ok': False, 'error': diagnostics.exception_details(exc)}), encoding='utf-8')
            return 1
        message = tr("Не удалось открыть Director Calendar.")
        if diagnostics.record_error('startup', exc):
            log = diagnostics.log_path()
            message += tr("\n\nПодробности ошибки сохранены в:\n{0}").format(log)
        else:
            message += tr("\n\nНе удалось сохранить подробности ошибки. Проверь доступ к папке данных приложения.")
        show_message(message, error=True)
        return 1
    finally:
        diagnostics.shutdown()

