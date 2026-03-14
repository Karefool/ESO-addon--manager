# ESO Power Lite

A lightweight, no-hassle addon manager for **Elder Scrolls Online**.

Browse thousands of ESO addons, install them with one click, and let ESO Power Lite handle all the library dependencies automatically. No more manually downloading LibStub, LibAddonMenu, or any other required libraries — they're installed for you.

## Features

- **One-Click Install** — Browse the full ESOUI addon catalog and install anything with a single click
- **Automatic Dependency Resolution** — Required libraries (DependsOn + OptionalDependsOn) are detected and installed automatically
- **Uninstall from Anywhere** — Remove addons from the Discover tab, My Addons tab, or the addon detail view
- **Always Up to Date** — Addon catalog syncs automatically twice daily so you always see the latest versions
- **Lightweight & Fast** — Runs locally with a small SQLite database, no account required, no bloat
- **Self-Updating** — Get notified when a new version of ESO Power Lite is available

## Download

**[Download the latest release](https://github.com/Karefool/ESO-addon--manager/releases/latest)**

1. Download the `.zip` from the latest release
2. Extract it anywhere on your computer
3. Run `ESO_Power_Lite.exe`
4. Start installing addons!

No Python or any other software required. The app is fully standalone.

## How It Works

ESO Power Lite scans your local `Documents\Elder Scrolls Online\live\AddOns` folder to detect what you already have installed. When you install a new addon, it:

1. Downloads the addon ZIP directly from ESOUI
2. Extracts it to your AddOns folder
3. Reads the addon's manifest file for dependencies (`DependsOn` and `OptionalDependsOn`)
4. Automatically downloads and installs any missing libraries
5. Repeats recursively until all dependencies are resolved

## Feedback & Support

- **Found a bug or have a feature request?** [Open an issue](https://github.com/Karefool/ESO-addon--manager/issues)
- **Want to support development?** [Buy me a coffee via PayPal](https://www.paypal.com/paypalme/my/profile)

## Tech Stack

Built with Python (FastAPI + pywebview), React, TypeScript, and Tailwind CSS. Addon data sourced from [ESOUI](https://www.esoui.com/) and synced via GitHub Actions.

## License

This project is open source and available for personal use.
