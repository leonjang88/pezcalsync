"""
py2app setup script for PezCalSync

Build with:
    cd /Users/leonjang/calendar-tool
    source venv/bin/activate
    python build_app.py py2app

This creates a self-contained macOS app bundle with Python and all dependencies.
"""

from setuptools import setup

APP = ['src/calendar_menubar.py']
DATA_FILES = []

OPTIONS = {
    'argv_emulation': False,  # Disable for menubar apps
    'iconfile': None,  # Add icon path here if you have one
    'plist': {
        'CFBundleName': 'PezCalSync',
        'CFBundleDisplayName': 'Pez Cal Sync',
        'CFBundleIdentifier': 'com.leonjang.pezcalsync',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': True,  # Hide from dock (menubar app)
        'NSHighResolutionCapable': True,
        # Calendar permissions
        'NSCalendarsUsageDescription': 'PezCalSync needs access to your calendars to sync personal calendar events to your work calendar.',
        'NSCalendarsFullAccessUsageDescription': 'PezCalSync needs full access to your calendars to read and create calendar events.',
    },
    'includes': [
        'rumps',
        'calendar_sync_eventkit',
        'settings_window',
        'pkg_resources',
        'objc',
        'EventKit',
        'Foundation',
        'AppKit',
    ],
    'excludes': [
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'PIL',
        # Exclude Google API libraries - not needed anymore
        'google.auth',
        'google.oauth2',
        'google_auth_oauthlib',
        'googleapiclient',
        'httplib2',
    ],
    'resources': ['src/icons'],
    'semi_standalone': False,  # Full standalone app
    'site_packages': True,
}

setup(
    name='PezCalSync',
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
