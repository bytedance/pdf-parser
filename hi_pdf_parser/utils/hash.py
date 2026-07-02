# Copyright (C) 2025 ByteDance Inc
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import hashlib
import json
from enum import Enum, auto


class HashType(Enum):
    SHA3_256 = auto()
    SHA_256 = auto()
    MD5 = auto()
    SHA1 = auto()


def generate_hash(
    content: str | bytes | dict, hash_type: HashType = HashType.SHA3_256
) -> str:
    if isinstance(content, str):
        content_bytes = content.encode("utf-8")
    elif isinstance(content, dict):
        # Use stable JSON for consistent hash
        content_bytes = json.dumps(
            content, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    elif isinstance(content, bytes):
        content_bytes = content
    else:
        raise ValueError(f"Unsupported type for hashing: {type(content)}")

    if hash_type == HashType.SHA_256:
        hash_obj = hashlib.sha256(content_bytes)
    elif hash_type == HashType.MD5:
        hash_obj = hashlib.md5(content_bytes)
    elif hash_type == HashType.SHA1:
        hash_obj = hashlib.sha1(content_bytes)
    else:
        hash_obj = hashlib.sha3_256(content_bytes)

    return hash_obj.hexdigest()
