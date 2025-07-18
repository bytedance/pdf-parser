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
