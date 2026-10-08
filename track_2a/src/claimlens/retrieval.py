"""Local lexical retrieval over exact source spans, without model dependencies.

Cached statistics contain neither gold labels nor predictions. Returned units
always come from the current source text; ranking never rewrites a quotation.
"""

from collections import Counter, OrderedDict, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import unicodedata

from .llm import text_spans


ALGORITHM_VERSION = "claimlens-bm25-1"
CACHE_DIRECTORY = Path(tempfile.gettempdir()) / "claimlens-retrieval-v1"
MAX_CACHE_BYTES = 16_000_000
MAX_MEMORY_ENTRIES = 8
_MEMORY_CACHE = OrderedDict()
_CACHE_LOCK = threading.RLock()
_METADATA = ("id", "text", "page", "language", "title", "attribution")
# Negation, amounts and quantifiers remain searchable. These are function words,
# not translations or a semantic classifier.
_STOPWORDS = frozenset("""
der die das den dem des ein eine einer eines einen einem und oder im in am an
auf aus bei bis durch fur mit von vom zu zum zur ist sind wird werden
le la les un une des du de d l et ou au aux en a par pour sur dans est sont
il lo gli i un uno una del dello della dei degli delle di e o ed al alla alle
ai agli con da dal dalla per su sul sulla nel nella nei nelle che si
the a an and or of to for from with on in is are be this that
""".split())


def _normalized(text):
    return "".join(character for character in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.combining(character))


def _words(text):
    return [word for word in re.findall(r"[^\W_]+", _normalized(text), re.UNICODE)
            if word not in _STOPWORDS and (len(word) > 1 or word.isdigit()) and len(word) <= 80]


def _grams(words):
    return {word[index:index + 3] for word in words if len(word) >= 4 and not word.isdigit()
            for index in range(len(word) - 2)}


def _units(passages):
    units = []
    for passage in passages:
        for start, end, text in text_spans(passage["text"]):
            units.append({"id": "u{}".format(len(units) + 1), "passage_id": passage["id"],
                          "page": passage.get("page"), "language": passage.get("language"),
                          "title": passage.get("title"), "attribution": passage.get("attribution"),
                          "start": start, "end": end, "text": text})
    return units


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _key(passages):
    return hashlib.sha256(_encoded({"algorithm": ALGORITHM_VERSION,
        "passages": [{field: passage.get(field) for field in _METADATA} for passage in passages]})).hexdigest()


def _build_index(units):
    lengths, terms, grams = [], defaultdict(list), defaultdict(list)
    for position, unit in enumerate(units):
        words = _words(unit["text"])
        lengths.append(len(words))
        for word, count in Counter(words).items():
            terms[word].append([position, count])
        for gram in sorted(_grams(words)):
            grams[gram].append(position)
    return {"unit_count": len(units), "lengths": lengths, "terms": dict(terms), "grams": dict(grams)}


def _valid_index(index, count):
    if not isinstance(index, dict) or index.get("unit_count") != count:
        return False
    lengths = index.get("lengths")
    if (not isinstance(lengths, list) or len(lengths) != count or
            any(type(value) is not int or not 0 <= value <= 900 for value in lengths)):
        return False
    for field in ("terms", "grams"):
        entries = index.get(field)
        if not isinstance(entries, dict) or len(entries) > 300_000:
            return False
        for term, postings in entries.items():
            if not isinstance(term, str) or not 1 <= len(term) <= 80 or not isinstance(postings, list):
                return False
            previous = -1
            for posting in postings:
                if field == "terms":
                    if not isinstance(posting, list) or len(posting) != 2:
                        return False
                    position, frequency = posting
                    if (type(frequency) is not int or frequency < 1 or
                            type(position) is not int or not 0 <= position < count or
                            frequency > lengths[position]):
                        return False
                else:
                    position = posting
                if type(position) is not int or not previous < position < count:
                    return False
                previous = position
    return True


def _load_index(key, count):
    path = CACHE_DIRECTORY / (key + ".json")
    try:
        if CACHE_DIRECTORY.is_symlink() or path.is_symlink() or path.stat().st_size > MAX_CACHE_BYTES:
            return None
        with path.open("rb") as stream:
            raw = stream.read(MAX_CACHE_BYTES + 1)
        if len(raw) > MAX_CACHE_BYTES:
            return None
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or envelope.get("key") != key or envelope.get("algorithm") != ALGORITHM_VERSION:
            return None
        index = envelope.get("index")
        if not _valid_index(index, count):
            return None
        if envelope.get("index_sha256") != hashlib.sha256(_encoded(index)).hexdigest():
            return None
        return index
    except (OSError, ValueError, TypeError, RecursionError):
        return None


def _store_index(key, index):
    temporary = None
    try:
        if CACHE_DIRECTORY.is_symlink():
            return
        CACHE_DIRECTORY.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = CACHE_DIRECTORY / (key + ".json")
        if path.is_symlink():
            return
        content = _encoded({"algorithm": ALGORITHM_VERSION, "key": key,
                            "index_sha256": hashlib.sha256(_encoded(index)).hexdigest(), "index": index})
        if len(content) > MAX_CACHE_BYTES:
            return
        with tempfile.NamedTemporaryFile("wb", dir=CACHE_DIRECTORY, prefix=".index-", delete=False) as stream:
            temporary = stream.name
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        # A read-only or unavailable cache must not disable inference.
        pass
    finally:
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass


def _index_for(key, units):
    with _CACHE_LOCK:
        if key in _MEMORY_CACHE:
            _MEMORY_CACHE.move_to_end(key)
            return _MEMORY_CACHE[key], True
        index = _load_index(key, len(units))
        hit = index is not None
        if index is None:
            index = _build_index(units)
            _store_index(key, index)
        _MEMORY_CACHE[key] = index
        while len(_MEMORY_CACHE) > MAX_MEMORY_ENTRIES:
            _MEMORY_CACHE.popitem(last=False)
        return index, hit


def _scores(index, queries):
    """BM25 plus a small substring fallback for inflection and compounds."""
    count = index["unit_count"]
    scores = [0.0] * count
    if not count:
        return scores
    query_words = {_word for query in queries for _word in _words(query)}
    average = sum(index["lengths"]) / count or 1.0
    for word in sorted(query_words):
        postings = index["terms"].get(word, [])
        inverse_frequency = math.log1p((count - len(postings) + 0.5) / (len(postings) + 0.5))
        # A wrong amount can be the decisive contradiction: it must not exclude
        # otherwise matching source content with a different amount.
        weight = 0.35 if word.isdigit() else 1.0
        for position, frequency in postings:
            denominator = frequency + 1.2 * (0.25 + 0.75 * index["lengths"][position] / average)
            scores[position] += weight * inverse_frequency * frequency * 2.2 / denominator
    # Score each language query separately so adding translations does not
    # dilute overlap with the document's actual language.
    fallback = [0.0] * count
    for query in queries:
        query_grams = _grams(_words(query))
        if len(query_grams) < 3:
            continue
        overlaps, values = Counter(), Counter()
        for gram in sorted(query_grams):
            postings = index["grams"].get(gram, [])
            inverse_frequency = math.log1p((count - len(postings) + 0.5) / (len(postings) + 0.5))
            for position in postings:
                overlaps[position] += 1
                values[position] += inverse_frequency
        for position, matches in overlaps.items():
            if matches >= max(3, math.ceil(len(query_grams) * 0.15)):
                fallback[position] = max(fallback[position], 0.2 * values[position] / len(query_grams))
    return [score + fallback[position] for position, score in enumerate(scores)]


def _page_key(unit):
    return (unit.get("page"), unit["passage_id"])


def _adjacent(first, second):
    if first["passage_id"] == second["passage_id"]:
        return first["end"] == second["start"] or second["end"] == first["start"]
    return (type(first.get("page")) is int and type(second.get("page")) is int
            and abs(first["page"] - second["page"]) == 1)


def search(passages, queries, vote_queries, limit=12):
    """Rank exact source units, including neighboring context within ``limit``.

    ``candidate_count`` counts lexical matches before diversity/neighbor limits.
    ``ranked_ids`` contains seeds in relevance order followed by neighbors; it
    never repeats a unit. A cache hit reuses index statistics, never a verdict.
    """
    if type(limit) is not int or limit < 0:
        raise ValueError("Retrieval limit must be a nonnegative integer.")
    queries = [query for query in queries if isinstance(query, str) and query.strip()]
    vote_queries = [query for query in vote_queries if isinstance(query, str) and query.strip()]
    units = _units(passages)
    key = _key(passages)
    index, cache_hit = _index_for(key, units)
    scores, votes = _scores(index, queries), _scores(index, vote_queries)
    page_votes = defaultdict(float)
    for position, unit in enumerate(units):
        page_votes[_page_key(unit)] = max(page_votes[_page_key(unit)], votes[position])
    scores = [score + 0.3 * page_votes[_page_key(units[position])]
              for position, score in enumerate(scores)]
    ranked = sorted((position for position, score in enumerate(scores) if score > 0),
                    key=lambda position: (-scores[position], position))
    candidate_count = len(ranked)
    reserve = max(1, limit // 3) if limit >= 3 else 0
    seed_limit = max(0, limit - reserve)
    seeds, page_counts = [], Counter()
    for position in ranked:
        if len(seeds) >= seed_limit:
            break
        page = _page_key(units[position])
        if page_counts[page] < 2:
            seeds.append(position)
            page_counts[page] += 1
    # If all matches occur on one page, do not waste the requested capacity.
    if len(seeds) < seed_limit:
        seeds.extend(position for position in ranked if position not in seeds)
        seeds = seeds[:seed_limit]
    chosen = set(seeds)
    neighbors = []
    neighbor_options = []
    for position in seeds:
        adjacent = [other for other in (position - 1, position + 1)
                    if 0 <= other < len(units) and _adjacent(units[position], units[other]) and other not in chosen]
        neighbor_options.append(sorted(adjacent, key=lambda other: (-scores[other], other)))
    # Round-robin gives several evidence sites context before adding both sides
    # of one site. No source text is synthesized or rewritten.
    for rank in range(2):
        for options in neighbor_options:
            if rank < len(options) and len(chosen) < limit and options[rank] not in chosen:
                chosen.add(options[rank])
                neighbors.append(options[rank])
    for position in ranked:
        if len(chosen) >= limit:
            break
        if position not in chosen:
            chosen.add(position)
            seeds.append(position)
    return {"units": units, "ranked_ids": [units[position]["id"] for position in seeds + neighbors],
            "cache_hit": cache_hit, "index_key": key, "candidate_count": candidate_count}
