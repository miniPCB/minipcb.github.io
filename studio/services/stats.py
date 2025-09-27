import re

def text_stats(text: str) -> dict:
    words = len(re.findall(r"\b\w+\b", text))
    sentences = len(re.findall(r"[.!?]+\s", text)) + (1 if text.strip() else 0)
    loc = sum(1 for line in text.splitlines() if line.strip())
    est_tokens = max(1, int(len(text) / 4))  # rough heuristic
    return {
        "words": words,
        "sentences": sentences,
        "loc": loc,
        "est_tokens": est_tokens
    }
