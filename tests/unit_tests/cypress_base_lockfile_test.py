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

import re
from pathlib import Path

from superset.utils import json

LOCKFILE_PATH = (
    Path(__file__).resolve().parents[2]
    / "superset-frontend/cypress-base/package-lock.json"
)


def test_cypress_base_lockfile_does_not_resolve_extract_zip() -> None:
    # GHSA-jmr9-qjv8-65gv and GHSA-7pqw-9j4j-h8q3 affect every published
    # extract-zip release (<=2.0.1), so no version of it is acceptable.
    packages: dict[str, dict[str, str]] = json.loads(LOCKFILE_PATH.read_text())[
        "packages"
    ]
    extract_zip_entries = [
        f"{location}@{package.get('version')}"
        for location, package in packages.items()
        if re.search(r"(^|/)node_modules/extract-zip$", location)
    ]

    assert extract_zip_entries == []
