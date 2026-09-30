/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import fs from 'fs';
import path from 'path';

type LockfilePackage = { version?: string };

const lockfile: { packages: Record<string, LockfilePackage> } = JSON.parse(
  fs.readFileSync(
    path.resolve(__dirname, '../../cypress-base/package-lock.json'),
    'utf8',
  ),
);

// GHSA-jmr9-qjv8-65gv and GHSA-7pqw-9j4j-h8q3 affect every published
// extract-zip release (<=2.0.1), so no version of it is acceptable.
test('cypress-base lockfile does not resolve extract-zip', () => {
  const extractZipEntries = Object.entries(lockfile.packages)
    .filter(([location]) => /(^|\/)node_modules\/extract-zip$/.test(location))
    .map(([location, pkg]) => `${location}@${pkg.version}`);

  expect(extractZipEntries).toEqual([]);
});
