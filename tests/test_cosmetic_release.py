"""A focused release must be explainable solely by changes to display literals."""
import pytest

from scripts.cosmetic_release import cosmetic_file


THEME = 'director_control/theme.py'
BOARD = 'director_control/calendar_view.py'
CATALOG = 'director_control/english.py'
PALETTE = 'LIGHT = {"frozen_day": "#E6EAF2"}\nDARK = {**LIGHT, "frozen_day": "#31463B"}\n'
IMPORT = 'from .widget_text import localized\n'
BOARD_TEXT = IMPORT + 'class CalendarBoard:\n    def __init__(self):\n        localized(self, toolTip="Green")\n'
DICTIONARY = '"""English strings."""\nMESSAGES = {"До": "Before", "По": "To"}\n'


def test_only_color_values_of_existing_palette_entries_can_change():
    assert cosmetic_file(THEME, PALETTE, PALETTE.replace('#E6EAF2', '#EEE8F5').replace('#31463B', '#453d55'))
    for change in ('"<color>"', '"red"', 'None', 'rgb()', '"#12345z"'):
        assert not cosmetic_file(THEME, PALETTE, PALETTE.replace('"#E6EAF2"', change))
    assert not cosmetic_file(THEME, PALETTE, PALETTE.replace('frozen_day', 'today'))
    assert not cosmetic_file(THEME, PALETTE, PALETTE.replace('**LIGHT', '**OTHER'))
    assert not cosmetic_file(THEME, PALETTE, PALETTE + 'print("changed")')
    assert not cosmetic_file(THEME, PALETTE, PALETTE.replace('"#E6EAF2"', '"#EEEEEE", "extra": "#AAAAAA"'))


def test_calendar_tooltip_and_other_literal_widget_captions():
    assert cosmetic_file(BOARD, BOARD_TEXT, BOARD_TEXT.replace('Green', 'Lavender'))
    original = IMPORT + 'button = localized(QPushButton(), text="Done", accessibleName="Mark done")'
    assert cosmetic_file('director_control/inspector.py', original, original.replace('"Done"', '"Complete"'))
    assert not cosmetic_file('director_control/storage.py', original, original.replace('"Done"', '"Complete"'))


@pytest.mark.parametrize('before,after', [
    ('localized(self, title="Title")', 'localized(other, title="Title")'),
    ('localized(self, title="Title")', 'localized(self, title=lookup("New"))'),
    ('localized(self, extra="Before")', 'localized(self, extra="After")'),
    ('localized(self, text="Before")', 'localized(self, title="After")'),
    ('localized(make("Before"), text="Old")', 'localized(make("After"), text="New")'),
    ('store.load("Before")', 'store.load("After")'),
])
def test_mixed_or_non_presentation_arguments_run_full(before, after):
    assert not cosmetic_file(BOARD, IMPORT + before, IMPORT + after)


@pytest.mark.parametrize('binding', [
    '', 'from other import localized\n', IMPORT + 'from other import *\n',
    IMPORT + 'from other import function as localized\n', IMPORT + 'localized = other\n',
    IMPORT + 'def show(localized):\n    ', IMPORT + 'def localized(*args, **kwargs): pass\n',
])
def test_helper_requires_unambiguous_import(binding):
    text = binding + 'localized(self, text="Old")'
    assert not cosmetic_file(BOARD, text, text.replace('"Old"', '"New"'))


def test_catalog_accepts_only_data_and_handles_changed_source_labels():
    updated = DICTIONARY.replace('"До": "Before"', '"После": "After"')
    assert cosmetic_file(CATALOG, DICTIONARY, updated)
    assert not cosmetic_file(CATALOG, DICTIONARY, updated.replace('English strings.', 'Modified module.'))
    for code in ('import sys', 'MESSAGES.update({"extra": "Entry"})'):
        assert not cosmetic_file(CATALOG, DICTIONARY, updated + code)


@pytest.mark.parametrize('value', [
    None, '', '!', 'MESSAGES = {"one": first()}', 'MESSAGES = {"a": "A", **other}',
    'MESSAGES = {"a": "A", "a": "B"}', 'MESSAGES = {1: "One"}',
    'other = MESSAGES = {"key": "text"}', 'MESSAGES = {key: key for key in names}',
])
def test_missing_or_ambiguous_catalog_runs_full(value):
    assert not cosmetic_file(CATALOG, DICTIONARY, value)
    assert not cosmetic_file(CATALOG, value, DICTIONARY)


def test_unchanged_whitespace_and_unrecognized_files_do_not_grant_focused_release():
    assert not cosmetic_file(BOARD, BOARD_TEXT, BOARD_TEXT + '\n')
    assert not cosmetic_file('scripts/new.py', 'from a import b', 'from a import c')
