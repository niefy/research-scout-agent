from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter

_WHITESPACE_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+")

_CN_STOPWORDS = {
    "我们",
    "你们",
    "他们",
    "以及",
    "但是",
    "因为",
    "所以",
    "如果",
    "已经",
    "可以",
    "这个",
    "那个",
    "一个",
    "没有",
    "不是",
    "就是",
    "还是",
    "对于",
    "关于",
    "表示",
    "认为",
    "目前",
    "今日",
    "公司",
    "市场",
    "方面",
    "进行",
    "相关",
    "通过",
    "同时",
    "此外",
    "其中",
    "由于",
    "根据",
    "数据显示",
    "记者",
    "报道",
    "证券",
    "日报",
    "时报",
}


def clean_text(text: str) -> str:
    """Strip markup and collapse whitespace while preserving Chinese punctuation."""
    text = text or ""
    text = _TAG_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = text.replace("　", " ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_text(text: str) -> str:
    """Canonical form used for hashing, matching and tokenization."""
    return unicodedata.normalize("NFKC", clean_text(text))


def content_hash(title: str, content: str) -> str:
    payload = f"{normalize_text(title)}\n{normalize_text(content)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_external_id(url: str, title: str) -> str:
    raw = f"{url}\n{normalize_text(title)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _tokens(text: str) -> list[str]:
    text = normalize_text(text).lower()
    tokens: list[str] = []
    tokens.extend(re.findall(r"[a-z0-9][a-z0-9._-]{1,15}", text))
    chunks = re.findall(r"[一-鿿]+", text)
    for chunk in chunks:
        if len(chunk) == 1:
            continue
        for size in (2, 3):
            for i in range(0, len(chunk) - size + 1):
                token = chunk[i : i + size]
                if token not in _CN_STOPWORDS:
                    tokens.append(token)
    return tokens


def simhash64(text: str) -> str:
    """Return a 64-bit SimHash as 16 hex characters."""
    vector = [0] * 64
    counts = Counter(_tokens(text))
    if not counts:
        return "0" * 16
    for token, weight in counts.items():
        digest = hashlib.md5(token.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], "big")
        for bit in range(64):
            vector[bit] += weight if (value >> bit) & 1 else -weight
    result = 0
    for bit in range(64):
        if vector[bit] > 0:
            result |= 1 << bit
    return f"{result:016x}"


def hamming_distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


_KEYWORD_CHAR_RE = re.compile(r"[一-鿿A-Za-z]")


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    """Extract readable keywords with jieba's TF-IDF ranking.

    Character n-grams are useful for SimHash, but produce broken words such as
    "比增长" when shown to users. Jieba returns real word boundaries instead.
    """
    import logging

    import jieba
    from jieba import analyse

    jieba.setLogLevel(logging.WARNING)
    cleaned = clean_text(text)
    if not cleaned:
        return []

    candidates = analyse.extract_tags(cleaned, topK=limit * 3)
    keywords: list[str] = []
    for token in candidates:
        token = token.strip()
        if len(token) < 2 or len(token) > 16:
            continue
        if token in _CN_STOPWORDS or not _KEYWORD_CHAR_RE.search(token):
            continue
        if any(token in existing or existing in token for existing in keywords):
            continue
        keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


def truncate(text: str, limit: int) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
