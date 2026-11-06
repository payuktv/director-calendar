"""Windows desktop entry point for Director Control."""


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ['--calendar-worker']:
        from director_control.sync_process import worker_main
        raise SystemExit(worker_main())
    from director_control.launcher import main
    raise SystemExit(main())
