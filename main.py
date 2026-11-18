"""Windows desktop entry point for Director Control."""


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] == ['--verify-update-version']:
        from director_control import __version__
        from director_control.runtime_versions import runtime_versions, verify_runtime
        from PySide6.QtCore import qVersion
        verify_runtime(runtime_versions())
        raise SystemExit(0 if sys.argv[2:] == [__version__] and qVersion() else 1)
    if sys.argv[1:2] == ['--prepare-update']:
        from director_control.package_update import worker_main
        raise SystemExit(worker_main(sys.argv[2:]))
    if sys.argv[1:] == ['--calendar-worker']:
        from director_control.sync_process import worker_main
        raise SystemExit(worker_main())
    from director_control.launcher import main
    raise SystemExit(main())
