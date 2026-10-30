"""GUI entry point with a visible error if startup fails without a console."""
import sys
import traceback

from .desktop import show_message
from .storage import default_data_dir


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--verify-installation':
            from .distribution_check import verify_installation
            return verify_installation(sys.argv[2])
        from .windows_lifecycle import hold_installer_mutex
        hold_installer_mutex()
        from .ui import run_app
        return run_app()
    except Exception:
        details = traceback.format_exc()
        message = "Не удалось открыть Director Calendar."
        try:
            log = default_data_dir() / "startup-error.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(details, encoding="utf-8")
            message += f"\n\nПодробности ошибки сохранены в:\n{log}"
        except OSError:
            message += "\n\nНе удалось сохранить подробности ошибки. Проверь доступ к папке данных приложения."
        if sys.stderr is not None:
            sys.stderr.write(details)
        show_message(message, error=True)
        return 1

