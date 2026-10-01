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
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anyio.abc import ByteStream
from anyio.streams.tls import TLSAttribute, TLSStream


@pytest.mark.parametrize(
    ("hostname", "expected_hostname"),
    [
        ("faß.example", "xn--fa-hia.example"),
        ("fass.example", "fass.example"),
    ],
)
def test_tls_certificate_hostname_uses_idna2008(
    hostname: str, expected_hostname: str
) -> None:
    """TLS certificate matching must preserve distinct IDNA 2008 hostnames."""
    transport = MagicMock(spec=ByteStream)
    with patch.object(TLSStream, "_call_sslobject_method", new_callable=AsyncMock):
        stream = asyncio.run(TLSStream.wrap(transport, hostname=hostname))

    ssl_object = stream.extra(TLSAttribute.ssl_object)  # noqa: S610
    assert ssl_object.server_hostname == expected_hostname
