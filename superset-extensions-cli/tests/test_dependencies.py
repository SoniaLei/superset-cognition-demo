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

from __future__ import annotations

import tomllib
from typing import Any
from pathlib import Path

from packaging.requirements import Requirement

REPO_ROOT = Path(__file__).resolve().parents[2]

# apache-superset-core 0.1.0 on PyPI predates `Manifest.id` becoming a computed
# field, so the manifest built by this CLI fails validation against it.
INCOMPATIBLE_CORE_VERSION = "0.1.0"


def _read_pyproject(path: Path) -> dict[str, Any]:
    """Load a pyproject.toml file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def _core_requirement() -> Requirement:
    """Return the CLI's declared apache-superset-core requirement."""
    pyproject = _read_pyproject(REPO_ROOT / "superset-extensions-cli/pyproject.toml")
    for dependency in pyproject["project"]["dependencies"]:
        requirement = Requirement(dependency)
        if requirement.name == "apache-superset-core":
            return requirement
    raise AssertionError("apache-superset-core is not a CLI dependency")


def test_core_requirement_excludes_incompatible_release() -> None:
    """The CLI must not resolve a core whose Manifest still requires `id`."""
    assert not _core_requirement().specifier.contains(INCOMPATIBLE_CORE_VERSION)


def test_core_requirement_accepts_in_repo_core() -> None:
    """The CLI must be installable alongside the in-repo superset-core."""
    core_version = _read_pyproject(REPO_ROOT / "superset-core/pyproject.toml")[
        "project"
    ]["version"]
    assert _core_requirement().specifier.contains(core_version)
