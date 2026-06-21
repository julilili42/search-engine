from __future__ import annotations

MODEL_NAME = "distilbert-base-uncased"

_MAX_CHARS = 2_000
_SIM_FLOOR = 0.65

_TOPIC_SENTENCES = (
    "Tübingen is a university town on the river Neckar in southern Germany.",
    "The medieval old town of Tübingen with its market square and castle.",
    "Sightseeing, attractions and landmarks in and around Tübingen.",
    "Restaurants, cafes, food and drinks in Tübingen.",
    "The University of Tübingen, its institutes, research and student life.",
    "History, culture and events of the city of Tübingen.",
)

_MODEL = None
_TOKENIZER = None
_PROTOTYPE = None  

def _load() -> None:
    global _MODEL, _TOKENIZER, _PROTOTYPE
    if _MODEL is not None:
        return

    import torch
    from transformers import AutoModel, AutoTokenizer

    _TOKENIZER = AutoTokenizer.from_pretrained(MODEL_NAME)
    _MODEL = AutoModel.from_pretrained(MODEL_NAME)
    _MODEL.eval()

    with torch.no_grad():
        _PROTOTYPE = _embed(list(_TOPIC_SENTENCES)).mean(dim=0)
        _PROTOTYPE = _PROTOTYPE / _PROTOTYPE.norm()

def _embed(texts: list[str]):
    import torch

    encoded = _TOKENIZER(
        texts,
        padding=True,
        truncation=True,
        max_length=512,
        return_tensors="pt",
    )
    with torch.no_grad():
        tokens = _MODEL(**encoded).last_hidden_state  

    mask = encoded["attention_mask"].unsqueeze(-1).float()
    summed = (tokens * mask).sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1e-9)
    pooled = summed / counts
    return pooled / pooled.norm(dim=1, keepdim=True).clamp(min=1e-9)

# 0 -> unrelated, 1 -> perfect tübingen match
def topic_similarity(title: str, text: str) -> float:
    _load()

    snippet = f"{title}\n{text}"[:_MAX_CHARS]
    cosine = float(_embed([snippet])[0] @ _PROTOTYPE)

    # rescale to [0, 1]
    calibrated = (cosine - _SIM_FLOOR) / (1.0 - _SIM_FLOOR)
    return min(1.0, max(0.0, calibrated))
