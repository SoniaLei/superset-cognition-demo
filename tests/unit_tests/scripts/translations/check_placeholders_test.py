# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
"""
Tests for ``scripts/translations/check_placeholders.py``.

The script is not installed as a package, so it is loaded via importlib from
its on-disk path, matching ``check_translation_regression_test.py``.
"""

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "translations" / "check_placeholders.py"
_spec = importlib.util.spec_from_file_location("check_placeholders", _SCRIPT_PATH)
assert _spec is not None, f"Could not load {_SCRIPT_PATH}"
assert _spec.loader is not None, f"No loader on spec for {_SCRIPT_PATH}"
check_placeholders = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_placeholders)

_HEADER = (
    'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n'
    '"Plural-Forms: nplurals=2; plural=(n != 1);\\n"\n\n'
)


def _write_po(tmp_path: Path, lang: str, body: str) -> Path:
    po_file = tmp_path / lang / "LC_MESSAGES" / "messages.po"
    po_file.parent.mkdir(parents=True)
    po_file.write_text(_HEADER + body, encoding="utf-8")
    return po_file


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Running block %(block_num)s out of %(block_count)s",
            ["block_count", "block_num"],
        ),
        ("Created by: %s", [""]),
        ("%s rows, %d columns, %.2f%%", ["", "", ""]),
        ("% of total", []),
        ("(0% to 100%)", []),
    ],
)
def test_placeholders(text: str, expected: list[str]) -> None:
    assert sorted(check_placeholders.placeholders(text).elements()) == expected


def test_find_mismatches(tmp_path: Path) -> None:
    po_file = _write_po(
        tmp_path,
        "sk",
        "#, fuzzy, python-format\n"
        'msgid "Running block %(block_num)s out of %(block_count)s"\n'
        'msgstr "Spouští sa príkaz %(statement_num)s z %(statement_count)s"\n\n'
        "#, python-format\n"
        'msgid "Created by: %s"\n'
        'msgstr "Criado por"\n\n'
        'msgid "Not set"\n'
        'msgstr "Jeszcze brak %s"\n\n'
        "#, python-format\n"
        'msgid "Dataset %(table)s already exists"\n'
        'msgstr "Dataset %(table)s existuje"\n\n'
        "#, python-format\n"
        'msgid "%(num)s row"\n'
        'msgid_plural "%(num)s rows"\n'
        'msgstr[0] "jeden riadok"\n'
        'msgstr[1] "%(num)s riadkov"\n\n'
        'msgid "Untranslated %s"\n'
        'msgstr ""\n',
    )
    mismatches = check_placeholders.find_mismatches(po_file)
    assert [(m.msgid, m.fuzzy) for m in mismatches] == [
        ("Running block %(block_num)s out of %(block_count)s", True),
        ("Created by: %s", False),
        ("Not set", False),
    ]


def test_clear_fuzzy_blanks_only_fuzzy_mismatches(tmp_path: Path) -> None:
    po_file = _write_po(
        tmp_path,
        "sk",
        "# translator comment\n"
        "#: superset/sql_lab.py:588\n"
        "#, fuzzy, python-format\n"
        'msgid "Running block %(block_num)s out of %(block_count)s"\n'
        'msgstr ""\n'
        '"Spouští sa príkaz "\n'
        '"%(statement_num)s z %(statement_count)s"\n\n'
        "#, fuzzy\n"
        'msgid "Fuzzy but fine"\n'
        'msgstr "Fuzzy ale v poriadku"\n\n'
        "#, python-format\n"
        'msgid "Created by: %s"\n'
        'msgstr "Criado por"\n',
    )
    mismatches = check_placeholders.find_mismatches(po_file, clear_fuzzy=True)
    assert len(mismatches) == 2
    assert po_file.read_text(encoding="utf-8") == _HEADER + (
        "# translator comment\n"
        "#: superset/sql_lab.py:588\n"
        "#, python-format\n"
        'msgid "Running block %(block_num)s out of %(block_count)s"\n'
        'msgstr ""\n\n'
        "#, fuzzy\n"
        'msgid "Fuzzy but fine"\n'
        'msgstr "Fuzzy ale v poriadku"\n\n'
        "#, python-format\n"
        'msgid "Created by: %s"\n'
        'msgstr "Criado por"\n'
    )
    assert [m.msgid for m in check_placeholders.find_mismatches(po_file)] == [
        "Created by: %s"
    ]


def test_repo_catalogs_have_matching_placeholders() -> None:
    """Regression test for apache/superset-style issue #6.

    Every translation shipped in ``superset/translations`` must be formattable
    with the arguments of its English source; a mismatch raises ``KeyError`` in
    the backend (e.g. SQL Lab in Slovak) or shows a raw ``%s`` in the UI.
    """
    mismatches = check_placeholders.check_translations_dir(
        _REPO_ROOT / "superset" / "translations"
    )
    assert not mismatches, "\n".join(str(m) for m in mismatches)
