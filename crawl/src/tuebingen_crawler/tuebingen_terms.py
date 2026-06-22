from __future__ import annotations
import re

# multiple variants
TUEBINGEN_RE = re.compile(r"t[üu]e?bingen", re.IGNORECASE)
# relevant named entities without tübingen in it
NAMED_ENTITIES = (
    "bebenhausen", "neckarfront", "stocherkahn", "hölderlin",
    "chocolart", "eberhard karls",
    "lustnau", "derendingen", "unterjesingen", "hagelloch", "pfrondorf",
    "cyber valley", "neckarinsel", "steinlach", "wurmlinger kapelle",
    "schwärzloch", "kupferbau", "wilhelmsstift",
)

def has_tuebingen(s: str) -> bool:
    s = s.lower()
    return bool(TUEBINGEN_RE.search(s)) or any(n in s for n in NAMED_ENTITIES)

def tuebingen_hits(s: str) -> int:
    s = s.lower()
    return len(TUEBINGEN_RE.findall(s)) + sum(s.count(n) for n in NAMED_ENTITIES)
