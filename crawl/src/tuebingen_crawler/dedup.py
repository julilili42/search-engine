import hashlib
import re

_TOKEN_RE = re.compile(r"[a-zäöüß0-9]+", re.IGNORECASE)
SIMHASH_BITS = 64

# two documents are near-duplicates if <= NEAR_DUP_HAMMING
NEAR_DUP_HAMMING = 3
_MASK = (1 << SIMHASH_BITS) - 1

# returns n-grams
def _shingles(text: str, n: int = 3) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    if len(tokens) < n:
        return tokens
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]

def _hash_feature(feature: str) -> int:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")

def _hamming_distance(a: int, b: int) -> int:
    return ((a ^ b) & _MASK).bit_count()

# returns a simhash fingerprint of the text
def simhash(text: str) -> int:
    counts = [0] * SIMHASH_BITS
    features = _shingles(text)
    if not features:
        return 0

    for feature in features:
        h = _hash_feature(feature)
        for bit in range(SIMHASH_BITS):
            if h & (1 << bit):
                counts[bit] += 1
            else:
                counts[bit] -= 1

    fingerprint = 0
    for bit in range(SIMHASH_BITS):
        if counts[bit] > 0:
            fingerprint |= 1 << bit
    return fingerprint

# true if fingerprint is within threshold of any seen element
def is_near_duplicate(fingerprint: int, seen: set[int], threshold: int = NEAR_DUP_HAMMING) -> bool:
    return any(_hamming_distance(fingerprint, other) <= threshold for other in seen)