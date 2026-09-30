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
Check that translated strings keep the placeholders of their English source.

Superset formats translations with ``%``-style placeholders on both the backend
(``flask_babel``: ``translation % kwargs``) and the frontend (``jed``
``sprintf``). A translation whose placeholders do not match its ``msgid``
either raises at runtime (``KeyError``/``TypeError``), renders a raw template
(``%s SENHA``) or silently drops a value. ``msgfmt -c`` does not catch this: it
skips fuzzy entries and entries without a ``python-format`` flag, and Superset
compiles fuzzy entries on purpose.

Rules
-----
* Named placeholders (``%(name)s``) used in a translated form must all exist in
  the source form it stands for (singular forms are compared with ``msgid``,
  plural forms with ``msgid_plural``), and none may be dropped.
* Positional placeholders (``%s``, ``%d``) must appear the same number of times.
* A translation may not mix positional and named placeholders when the source
  does not.
* Plural forms may spell out the count instead of using its single placeholder
  (``msgstr[0] "jeden riadok"`` for ``%(count)s row``), since the form is only
  ever used for that number.

Usage
-----
Report broken entries (exit 1 if any are found)::

    python scripts/translations/check_placeholders.py

Clear broken *fuzzy* entries in place, so they fall back to the English text.
Broken confirmed (non-fuzzy) entries are still reported and must be fixed by
hand::

    python scripts/translations/check_placeholders.py --fix
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TRANSLATIONS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "superset" / "translations"
)

SKIP_LANGS = {"en"}

# The space flag and the ``c``/``a``/``o``/``u`` conversions are deliberately
# left out: they never appear in Superset messages, and matching them would turn
# prose such as ``% calculation`` or ``0% to 100%`` into false placeholders.
_PLACEHOLDER_RE = re.compile(
    r"%(?:\((?P<name>[^)]*)\))?[-#0+]*(?:\*|\d+)?(?:\.(?:\*|\d+))?"
    r"(?P<conv>[dixXeEfFgGrs%])"
)


def extract_placeholders(text: str) -> tuple[list[str], int]:
    """Return ``(named placeholders, number of positional placeholders)``."""
    named: list[str] = []
    positional = 0
    for match in _PLACEHOLDER_RE.finditer(text):
        if match.group("conv") == "%" and match.group("name") is None:
            continue
        name = match.group("name")
        if name is None:
            positional += 1
        else:
            named.append(name)
    return named, positional


@dataclass
class Entry:
    msgid: str
    msgid_plural: str | None
    msgstr: dict[int, str]
    fuzzy: bool
    obsolete: bool
    lineno: int
    body_lines: list[str] = field(default_factory=list)


def _unquote(line: str) -> str:
    line = line.strip()
    if not (line.startswith('"') and line.endswith('"')):
        return ""
    inner = line[1:-1]
    return re.sub(
        r"\\(.)",
        lambda m: {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(
            m.group(1), m.group(1)
        ),
        inner,
    )


_KEY_RE = re.compile(r'^(msgctxt|msgid_plural|msgid|msgstr(?:\[(\d+)\])?)\s+(".*")$')


def parse_po(text: str) -> tuple[list[list[str]], list[Entry]]:
    """Split a .po file into blank-line separated blocks and parse each one.

    Returns the raw blocks (so callers can rewrite the file with minimal
    changes) and the parsed entries, one per block that contains a ``msgid``.
    """
    lines = text.split("\n")
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.strip() == "":
            if current:
                blocks.append(current)
                current = []
            blocks.append([line])
        else:
            current.append(line)
    if current:
        blocks.append(current)

    entries: list[Entry] = []
    lineno = 1
    for block in blocks:
        entry = _parse_block(block, lineno)
        if entry is not None:
            entries.append(entry)
        lineno += len(block)
    return blocks, entries


def _parse_fields(block: list[str]) -> tuple[dict[str, list[str]], bool, bool]:
    """Return ``(fields, fuzzy, obsolete)`` for one .po block."""
    fuzzy = False
    obsolete = False
    fields: dict[str, list[str]] = {}
    current_key: str | None = None
    for raw in block:
        line = raw
        if line.startswith("#~"):
            obsolete = True
            line = line[2:].lstrip()
        if line.startswith("#"):
            if line.startswith("#,") and "fuzzy" in line:
                fuzzy = True
            continue
        match = _KEY_RE.match(line)
        if match:
            current_key = match.group(1)
            fields[current_key] = [_unquote(match.group(3))]
        elif current_key is not None and line.strip().startswith('"'):
            fields[current_key].append(_unquote(line))
    return fields, fuzzy, obsolete


def _parse_block(block: list[str], lineno: int) -> Entry | None:
    fields, fuzzy, obsolete = _parse_fields(block)
    if "msgid" not in fields:
        return None
    msgstr: dict[int, str] = {}
    for key, parts in fields.items():
        if key == "msgstr":
            msgstr[0] = "".join(parts)
        elif key.startswith("msgstr["):
            msgstr[int(key[7:-1])] = "".join(parts)
    plural = fields.get("msgid_plural")
    return Entry(
        msgid="".join(fields["msgid"]),
        msgid_plural="".join(plural) if plural is not None else None,
        msgstr=msgstr,
        fuzzy=fuzzy,
        obsolete=obsolete,
        lineno=lineno,
        body_lines=block,
    )


def check_form(source: str, translation: str) -> str | None:
    """Return a description of the mismatch, or ``None`` if the form is fine."""
    src_named, src_pos = extract_placeholders(source)
    tr_named, tr_pos = extract_placeholders(translation)
    unknown = sorted(set(tr_named) - set(src_named))
    if unknown:
        return f"uses unknown placeholder(s) {unknown}"
    missing = sorted(set(src_named) - set(tr_named))
    if missing:
        return f"drops placeholder(s) {missing}"
    if src_pos != tr_pos:
        return f"has {tr_pos} positional placeholder(s), source has {src_pos}"
    if tr_named and src_pos:
        return "mixes named and positional placeholders"
    return None


def check_plural_form(msgid: str, msgid_plural: str, translation: str) -> str | None:
    """Check one form of a plural entry.

    gettext passes the same arguments to every form, so a form may use the
    placeholders of either source form (``Added 1 column`` / ``Added %s
    columns`` lets the singular form say ``%s`` too), may spell the count out
    instead of using its single placeholder, and only has to keep the
    placeholders that both source forms share.
    """
    if check_form(msgid, translation) is None:
        return None
    plural_problem = check_form(msgid_plural, translation)
    if plural_problem is None:
        return None
    sg_named, sg_pos = extract_placeholders(msgid)
    pl_named, pl_pos = extract_placeholders(msgid_plural)
    tr_named, tr_pos = extract_placeholders(translation)
    if (
        not tr_named
        and tr_pos == 0
        and 1 in {len(sg_named) + sg_pos, len(pl_named) + pl_pos}
    ):
        return None
    unknown = sorted(set(tr_named) - set(sg_named) - set(pl_named))
    if unknown:
        return f"uses unknown placeholder(s) {unknown}"
    missing = sorted((set(sg_named) & set(pl_named)) - set(tr_named))
    if missing:
        return f"drops placeholder(s) {missing}"
    if tr_pos not in {sg_pos, pl_pos}:
        return plural_problem
    return None


def check_entry(entry: Entry) -> list[str]:
    problems: list[str] = []
    if entry.obsolete or not entry.msgid:
        return problems
    for index, translation in sorted(entry.msgstr.items()):
        if not translation:
            continue
        if entry.msgid_plural is None:
            problem = check_form(entry.msgid, translation)
        else:
            problem = check_plural_form(entry.msgid, entry.msgid_plural, translation)
        if problem:
            problems.append(f"msgstr[{index}] {problem}")
    return problems


def clear_entry(entry: Entry) -> list[str]:
    """Return the block lines with every ``msgstr`` emptied and fuzzy unflagged."""
    out: list[str] = []
    skipping = False
    for line in entry.body_lines:
        if line.startswith("#,"):
            flags = [f.strip() for f in line[2:].split(",") if f.strip()]
            flags = [f for f in flags if f != "fuzzy"]
            if flags:
                out.append("#, " + ", ".join(flags))
            continue
        match = _KEY_RE.match(line)
        if match:
            skipping = match.group(1).startswith("msgstr")
            if skipping:
                out.append(f'{match.group(1)} ""')
                continue
        elif skipping and line.strip().startswith('"'):
            continue
        else:
            skipping = False
        out.append(line)
    return out


def check_file(po_file: Path, fix: bool = False) -> list[str]:
    """Return human-readable problems for ``po_file``; optionally fix fuzzies."""
    text = po_file.read_text(encoding="utf-8")
    blocks, entries = parse_po(text)
    problems: list[str] = []
    changed = False
    for entry in entries:
        entry_problems = check_entry(entry)
        if not entry_problems:
            continue
        if fix and entry.fuzzy:
            index = blocks.index(entry.body_lines)
            blocks[index] = clear_entry(entry)
            changed = True
            continue
        kind = "fuzzy" if entry.fuzzy else "confirmed"
        for problem in entry_problems:
            problems.append(
                f"{po_file}:{entry.lineno}: [{kind}] {problem}\n"
                f"    msgid  {entry.msgid!r}\n"
                f"    msgstr {entry.msgstr!r}"
            )
    if changed:
        po_file.write_text(
            "\n".join(line for block in blocks for line in block), encoding="utf-8"
        )
    return problems


def iter_po_files(translations_dir: Path) -> list[Path]:
    return sorted(
        po
        for po in translations_dir.glob("*/LC_MESSAGES/messages.po")
        if po.parent.parent.name not in SKIP_LANGS
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--translations-dir",
        type=Path,
        default=DEFAULT_TRANSLATIONS_DIR,
        help="Directory containing <lang>/LC_MESSAGES/messages.po",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Clear broken fuzzy entries in place (confirmed ones are reported)",
    )
    args = parser.parse_args(argv)

    problems: list[str] = []
    for po_file in iter_po_files(args.translations_dir):
        problems.extend(check_file(po_file, fix=args.fix))

    for problem in problems:
        print(problem)
    if problems:
        print(
            f"\n{len(problems)} translation(s) have placeholders that do not "
            "match their source string.",
            file=sys.stderr,
        )
        return 1
    print("All translation placeholders match their source strings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
