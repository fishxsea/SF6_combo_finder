"""Launch the browser by default; --cli selects the command-line interface."""
import sys


def check_browser():
    import asyncio
    from sf_combo_finder.combo_tui import ComboFinderApp

    async def check():
        app = ComboFinderApp(preferences_path=None, library_path=None)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            if 'ryu' not in app.characters:
                raise RuntimeError('Bundled roster failed to load')
    asyncio.run(check())


if __name__ == '__main__':
    if sys.argv[1:] == ['--check-installation']:
        check_browser()
        sys.exit(0)
    elif '--cli' in sys.argv[1:]:
        sys.argv.remove('--cli')
        from sf_combo_finder.combo_finder import main
    else:
        from sf_combo_finder.combo_tui import main
    main()
