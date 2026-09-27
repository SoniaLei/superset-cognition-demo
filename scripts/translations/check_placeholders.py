#!/usr/bin/env python3
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
Check that translated strings use the same ``%`` placeholders as their source.

Both the backend (``flask_babel``: ``msgstr % variables``) and the frontend
(``jed``/``sprintf``) substitute the *source* string's arguments into the
*translated* string. A translation whose placeholders differ from the source
therefore fails at runtime: a renamed ``%(name)s`` raises ``KeyError`` (a 500,
or a failed SQL Lab query), an extra ``%s`` is shown to the user verbatim, and
a missing placeholder silently drops a value.

Superset compiles and serves fuzzy translations, so fuzzy entries are checked
too — ``msgfmt -c`` skips them, which is why this class of bug went unnoticed.

Rules
-----
* A non-plural translation must contain exactly the placeholders of ``msgid``
  (same names, same counts).
* Each plural form may use any subset of the placeholders in ``msgid`` and
  ``msgid_plural``: gettext allows a form that stands for a single number
  (e.g. "one") to spell the number out instead of using ``%(num)s``. It must
  not introduce a placeholder that the source does not have.

Usage
-----
Report every mismatch and exit 1 if any were found::

    python scripts/translations/check_placeholders.py

Clear the *fuzzy* mismatches in place (they become untranslated, so the English
source with its values is shown instead). Confirmed mismatches are only
reported, since a human should fix the translation::

    python scripts/translations/check_placeholders.py --clear-fuzzy
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

import polib  # type: ignore[import-untyped]

DEFAULT_TRANSLATIONS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "superset" / "translations"
)

# English .po files use empty msgstr by convention (source language == target).
SKIP_LANGS = {"en"}

# ``%(name)s``, ``%s``, ``%d``, ``%.2f``... and the escaped ``%%``. Kept
# deliberately strict (no flag/width characters) so a literal "% of total" or
# "(0% to 100%)" is not mistaken for a conversion.
_PLACEHOLDER_RE = re.compile(r"%(?:\(([^)]+)\))?(?:\.\d+)?[sdifr]|%%")


def placeholders(text: str) -> Counter[str]:
    """Return the placeholder names in ``text`` (positional ones as ``""``)."""
    return Counter(
        match.group(1) or ""
        for match in _PLACEHOLDER_RE.finditer(text)
        if match.group(0) != "%%"
    )


class Mismatch(NamedTuple):
    po_file: Path
    msgid: str
    msgstr: str
    fuzzy: bool

    def __str__(self) -> str:
        flag = "fuzzy" if self.fuzzy else "confirmed"
        return (
            f"{self.po_file}: [{flag}]\n"
            f"  msgid  {self.msgid!r}\n"
            f"  msgstr {self.msgstr!r}"
        )


def find_mismatches(po_file: Path, *, clear_fuzzy: bool = False) -> list[Mismatch]:
    """Return the entries of ``po_file`` whose placeholders do not match.

    With ``clear_fuzzy`` the fuzzy mismatches are blanked and un-fuzzied in the
    file itself, leaving the rest of the catalog byte-for-byte untouched.
    """

    po = polib.pofile(str(po_file))
    mismatches: list[Mismatch] = []
    to_clear: set[tuple[str | None, str, str]] = set()
    for entry in po:
        if entry.obsolete or not entry.msgid:
            continue
        if entry.msgid_plural:
            allowed = placeholders(entry.msgid) | placeholders(entry.msgid_plural)
            forms = [form for form in entry.msgstr_plural.values() if form]
            bad = any(not placeholders(form) <= allowed for form in forms)
            shown = " | ".join(forms)
        else:
            bad = bool(entry.msgstr) and (
                placeholders(entry.msgstr) != placeholders(entry.msgid)
            )
            shown = entry.msgstr
        if not bad:
            continue
        fuzzy = "fuzzy" in entry.flags
        mismatches.append(Mismatch(po_file, entry.msgid, shown, fuzzy))
        if clear_fuzzy and fuzzy:
            to_clear.add((entry.msgctxt, entry.msgid, entry.msgid_plural))

    if to_clear:
        _clear_entries(po_file, to_clear)
    return mismatches


def _clear_entries(po_file: Path, targets: set[tuple[str | None, str, str]]) -> None:
    """Blank the given entries in ``po_file`` with a text-level edit.

    Neither ``polib`` nor the installed Babel round-trips these catalogs
    byte-for-byte (header wrapping differs), so the edit is done on the raw
    text of each entry block instead of re-serialising the whole file.
    """

    text = po_file.read_text(encoding="utf-8")
    blocks = text.split("\n\n")
    for i, block in enumerate(blocks):
        if "msgstr" not in block or block.lstrip().startswith("#~"):
            continue
        try:
            parsed = polib.pofile(block + "\n")
        except OSError:
            continue
        real = [e for e in parsed if e.msgid]
        if len(real) != 1:
            continue
        entry = real[0]
        if (entry.msgctxt, entry.msgid, entry.msgid_plural) not in targets:
            continue
        blocks[i] = _blank_block(block)
    po_file.write_text("\n\n".join(blocks), encoding="utf-8")


def _blank_block(block: str) -> str:
    lines = block.split("\n")
    out: list[str] = []
    in_msgstr = False
    for line in lines:
        if line.startswith("#,"):
            flags = [f.strip() for f in line[2:].split(",")]
            flags = [f for f in flags if f and f != "fuzzy"]
            if flags:
                out.append("#, " + ", ".join(flags))
            continue
        if line.startswith("msgstr"):
            in_msgstr = True
            out.append(re.sub(r'^(msgstr(?:\[\d+\])?) ".*"$', r'\1 ""', line))
            continue
        if in_msgstr and line.startswith('"'):
            continue  # continuation line of the msgstr being blanked
        in_msgstr = False
        out.append(line)
    return "\n".join(out)


def check_translations_dir(
    translations_dir: Path, *, clear_fuzzy: bool = False
) -> list[Mismatch]:
    mismatches: list[Mismatch] = []
    for po_file in sorted(translations_dir.glob("*/LC_MESSAGES/messages.po")):
        if po_file.parent.parent.name in SKIP_LANGS:
            continue
        mismatches.extend(find_mismatches(po_file, clear_fuzzy=clear_fuzzy))
    return mismatches


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--translations-dir", type=Path, default=DEFAULT_TRANSLATIONS_DIR
    )
    parser.add_argument(
        "--clear-fuzzy",
        action="store_true",
        help="blank fuzzy translations whose placeholders do not match",
    )
    args = parser.parse_args()

    mismatches = check_translations_dir(
        args.translations_dir, clear_fuzzy=args.clear_fuzzy
    )
    for mismatch in mismatches:
        print(mismatch)
    fuzzy = sum(m.fuzzy for m in mismatches)
    confirmed = len(mismatches) - fuzzy
    if args.clear_fuzzy:
        print(f"Cleared {fuzzy} fuzzy mismatch(es); {confirmed} confirmed remain.")
        sys.exit(1 if confirmed else 0)
    if mismatches:
        print(
            f"{len(mismatches)} translation(s) have placeholders that do not match "
            f"their source ({fuzzy} fuzzy, {confirmed} confirmed)."
        )
        sys.exit(1)
    print("All translation placeholders match their source strings.")


if __name__ == "__main__":
    main()
