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
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "translations" / "check_placeholders.py"
_spec = importlib.util.spec_from_file_location("check_placeholders", _SCRIPT_PATH)
assert _spec is not None, f"Could not load {_SCRIPT_PATH}"
assert _spec.loader is not None, f"No loader on spec for {_SCRIPT_PATH}"
check_placeholders = importlib.util.module_from_spec(_spec)
# dataclasses resolve postponed annotations through sys.modules
sys.modules[_spec.name] = check_placeholders
_spec.loader.exec_module(check_placeholders)

_HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'


def _write_po(tmp_path: Path, lang: str, body: str) -> Path:
    po = tmp_path / lang / "LC_MESSAGES" / "messages.po"
    po.parent.mkdir(parents=True)
    po.write_text(_HEADER + body, encoding="utf-8")
    return po


@pytest.mark.parametrize(
    ("source", "translation", "ok"),
    [
        ("Created by: %s", "Criado por: %s", True),
        ("Created by: %s", "Criado por", False),
        ("Not set", "Jeszcze brak %s", False),
        ("Dataset %(table)s already exists", "Dataset %(table)s bestaat al", True),
        ("Dataset %(table)s already exists", "Dataset %(name)s bestaat al", False),
        (
            "Running block %(block_num)s out of %(block_count)s",
            "Spouští sa príkaz %(statement_num)s z %(statement_count)s",
            False,
        ),
        ("Could not load driver for: %(engine)s", "Kon driver niet laden", False),
        ("%(count)s rows", "%(count)d Zeilen", True),
        ("100%% done", "100%% fertig", True),
        ("% calculation", "% Berechnung", True),
        ("0% to 100%", "0 % až 100 %", True),
        ("Value: %.2f", "Wert: %.2f", True),
        ("%s of %s", "%s / %s", True),
        ("%s of %s", "%s", False),
    ],
)
def test_check_form(source: str, translation: str, ok: bool) -> None:
    assert (check_placeholders.check_form(source, translation) is None) is ok


@pytest.mark.parametrize(
    ("translation", "ok"),
    [
        ("Afegida %s nova columna", True),
        ("Afegida una nova columna", True),
        ("Afegides %s noves columnes", True),
        ("Afegides %s de %s columnes", False),
    ],
)
def test_check_plural_form_singular_literal(translation: str, ok: bool) -> None:
    result = check_placeholders.check_plural_form(
        "Added 1 new column", "Added %s new columns", translation
    )
    assert (result is None) is ok


def test_check_plural_form_shares_arguments_across_forms() -> None:
    singular = '%(suggestion)s instead of "%(undefinedParameter)s?"'
    plural = (
        "%(firstSuggestions)s or %(lastSuggestion)s instead of "
        '"%(undefinedParameter)s"?'
    )
    assert (
        check_placeholders.check_plural_form(
            singular, plural, '%(lastSuggestion)s en lloc de "%(undefinedParameter)s?"'
        )
        is None
    )
    assert (
        check_placeholders.check_plural_form(
            singular, plural, "%(lastSuggestion)s en lloc de"
        )
        == "drops placeholder(s) ['undefinedParameter']"
    )
    assert (
        check_placeholders.check_plural_form(
            singular, plural, '%(other)s en lloc de "%(undefinedParameter)s?"'
        )
        == "uses unknown placeholder(s) ['other']"
    )


def test_check_file_reports_fuzzy_and_confirmed(tmp_path: Path) -> None:
    po = _write_po(
        tmp_path,
        "sk",
        '#, fuzzy\nmsgid "Running block %(block_num)s out of %(block_count)s"\n'
        'msgstr "Spúšťa sa %(statement_num)s z %(statement_count)s"\n\n'
        'msgid "Created by: %s"\nmsgstr "Vytvoril"\n\n'
        'msgid "Fine %s"\nmsgstr "Dobre %s"\n\n'
        '#~ msgid "Obsolete %s"\n#~ msgstr "Zastarané"\n',
    )
    problems = check_placeholders.check_file(po)
    assert len(problems) == 2
    assert "[fuzzy]" in problems[0]
    assert "statement_count" in problems[0]
    assert "[confirmed]" in problems[1]
    assert "Created by" in problems[1]


def test_fix_clears_only_broken_fuzzy_entries(tmp_path: Path) -> None:
    po = _write_po(
        tmp_path,
        "sk",
        "#: superset/sql_lab.py:1\n#, fuzzy, python-format\n"
        'msgid "Running block %(block_num)s out of %(block_count)s"\n'
        'msgstr ""\n"Spúšťa sa %(statement_num)s "\n"z %(statement_count)s"\n\n'
        '#, fuzzy\nmsgid "%(count)s rows"\nmsgid_plural "%(count)s rows"\n'
        'msgstr[0] "%(n)s riadok"\nmsgstr[1] "%(count)s riadky"\n\n'
        '#, fuzzy\nmsgid "Fine %s"\nmsgstr "Dobre %s"\n\n'
        'msgid "Created by: %s"\nmsgstr "Vytvoril"\n',
    )
    problems = check_placeholders.check_file(po, fix=True)
    assert len(problems) == 1
    assert "[confirmed]" in problems[0]
    assert po.read_text(encoding="utf-8") == (
        _HEADER + "#: superset/sql_lab.py:1\n#, python-format\n"
        'msgid "Running block %(block_num)s out of %(block_count)s"\n'
        'msgstr ""\n\n'
        'msgid "%(count)s rows"\nmsgid_plural "%(count)s rows"\n'
        'msgstr[0] ""\nmsgstr[1] ""\n\n'
        '#, fuzzy\nmsgid "Fine %s"\nmsgstr "Dobre %s"\n\n'
        'msgid "Created by: %s"\nmsgstr "Vytvoril"\n'
    )
    remaining = check_placeholders.check_file(po)
    assert len(remaining) == 1
    assert "Created by" in remaining[0]


def test_main_skips_english_and_exits_nonzero_on_problems(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_po(tmp_path, "en", 'msgid "Created by: %s"\nmsgstr ""\n')
    _write_po(tmp_path, "pl", 'msgid "Not set"\nmsgstr "Jeszcze brak %s"\n')
    assert check_placeholders.main(["--translations-dir", str(tmp_path)]) == 1
    assert "Jeszcze brak" in capsys.readouterr().out

    _write_po(tmp_path / "ok", "pl", 'msgid "Not set"\nmsgstr "Nie ustawiono"\n')
    assert check_placeholders.main(["--translations-dir", str(tmp_path / "ok")]) == 0


def test_repository_catalogs_have_matching_placeholders() -> None:
    """Every committed catalog must format with the arguments its source takes.

    A mismatch raises ``KeyError``/``TypeError`` at runtime (SQL Lab in Slovak
    failed with ``'statement_num'``) or shows a raw template to the user.
    """
    problems = [
        problem
        for po in check_placeholders.iter_po_files(
            _REPO_ROOT / "superset" / "translations"
        )
        for problem in check_placeholders.check_file(po)
    ]
    assert problems == [], "\n".join(problems)
