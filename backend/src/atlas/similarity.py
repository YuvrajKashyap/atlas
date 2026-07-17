import hashlib
import re

from atlas.enums import ChangeKind

TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}")


def simhash64(text: str) -> int:
    """Return a stable 64-bit SimHash over three-token shingles."""
    tokens = TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return 0
    shingles = (
        [" ".join(tokens[index : index + 3]) for index in range(len(tokens) - 2)]
        if len(tokens) >= 3
        else tokens
    )
    vector = [0] * 64
    for shingle in shingles:
        value = int.from_bytes(
            hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big"
        )
        for bit in range(64):
            vector[bit] += 1 if value & (1 << bit) else -1
    result = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            result |= 1 << bit
    return result


def encode_simhash(value: int) -> str:
    return f"{value & ((1 << 64) - 1):016x}"


def decode_simhash(value: str | None) -> int | None:
    return int(value, 16) if value else None


def simhash_bands(value: int) -> list[int]:
    return [(value >> (offset * 16)) & 0xFFFF for offset in range(4)]


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def classify_change(
    *,
    previous_hash: str | None,
    current_hash: str,
    previous_simhash: str | None,
    current_simhash: int,
    metadata_changed: bool,
) -> ChangeKind:
    if previous_hash is None:
        return ChangeKind.INITIAL
    if previous_hash == current_hash:
        return ChangeKind.METADATA_ONLY if metadata_changed else ChangeKind.UNCHANGED
    decoded = decode_simhash(previous_simhash)
    if decoded is not None and hamming_distance(decoded, current_simhash) <= 3:
        return ChangeKind.MINOR
    return ChangeKind.SUBSTANTIAL
