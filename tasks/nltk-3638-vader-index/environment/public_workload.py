"""Public-API workload for nltk-3638-vader-index. No timing, reward or expected answers here.

run(case, size, seed) builds a deterministic batch of documents from `seed`, scores every
document with nltk.sentiment.vader.SentimentIntensityAnalyzer().polarity_scores (the public
API), and returns digests of the scores. The VADER lexicon is the official nltk_data
sentiment/vader_lexicon.zip installed under /usr/share/nltk_data.

Cases
  transcripts  40 documents of `size` words each (earnings-call / meeting transcript scale).
  reviews      `size` documents of 120 words each (product-review scale).
  edge         fixed hand-written documents (repeated tokens, "kind of", "but", "least",
               negations, ALL CAPS, emoticons, punctuation, empty input); size/seed select a
               rotation of the list so every row is deterministic.
"""
import argparse
import hashlib
import itertools
import json
import random

STOP = ("the a an of to and in that is was for on it with as at by this be are from or have "
        "not but had they you we i he she").split()
BOOST = "very really extremely incredibly barely slightly kind of sort of".split()
NEG = "not never no isn't don't wasn't won't without".split()
SYLL = ["ka", "ro", "mi", "tel", "van", "sor", "pe", "lun", "dax", "qui", "bre", "nos", "fa", "git", "ul"]

EDGE = [
    "",
    "   ",
    "a",
    "good",
    "The food was good. The service was not good.",
    "not good at first, then good, then not good again, and good.",
    "I kind of liked it, but the kind staff were great and kind.",
    "kind kind kind of kind",
    "It was good but the ending was bad but the music was good.",
    "BUT it was GREAT, but not great, BUT great!!!",
    "At least it is good. The least good part was still good.",
    "least good, least bad, at least good, very least good",
    "never so good, never good, so good, never so bad",
    "very very bad, but great, very great, very bad",
    "GREAT great GREAT great Great!",
    "good, good! good. good? (good) good... good",
    ":) :) :( :) :D :( and :) again",
    "the bomb was the bomb, kiss of death, the bomb",
    "hand to mouth, yeah right, cut the mustard, hand to mouth",
    "cafe is wonderful été and the cafe is awful été wonderful",
    "No. no. NO! not no, never no, no good, no bad",
    "sux sux SUX! kinda sux but lol lol LOL",
    "I don't think it's not good, I don't think it's good, it's good",
    "Today kinda sux! But I'll get by, lol. Today kinda sux! But lol.",
]


def _scores_record(sia, docs, keep_raw):
    h = hashlib.sha256()
    compounds = []
    raw = []
    for d in docs:
        s = sia.polarity_scores(d)
        items = sorted(s.items())
        h.update(repr(items).encode())
        compounds.append(s["compound"])
        if keep_raw:
            raw.append([[k, v] for k, v in items])
    out = {
        "n_docs": len(docs),
        "n_words": sum(len(d.split()) for d in docs),
        "digest": h.hexdigest(),
        "compound_sum": round(sum(compounds), 6),
        "n_positive": sum(1 for c in compounds if c >= 0.05),
        "n_negative": sum(1 for c in compounds if c <= -0.05),
    }
    if keep_raw:
        out["scores"] = raw
    return out


def _generator(sia, seed):
    rng = random.Random(seed)
    lex = sorted(sia.lexicon)
    lexw = [w for w in lex if w.isalpha()]
    emo = [w for w in lex if not w.isalpha()][:200]
    content = ["".join(rng.choice(SYLL) for _ in range(rng.randint(2, 4))) for _ in range(20000)]
    cw = list(itertools.accumulate(1.0 / (i + 1) for i in range(len(content))))

    def word():
        r = rng.random()
        if r < 0.10:
            w = rng.choice(lexw)
        elif r < 0.45:
            w = rng.choice(STOP)
        elif r < 0.48:
            w = rng.choice(BOOST)
        elif r < 0.51:
            w = rng.choice(NEG)
        elif r < 0.515:
            w = rng.choice(emo)
        else:
            w = rng.choices(content, cum_weights=cw)[0]
        if rng.random() < 0.03:
            w = w.upper()
        p = rng.random()
        return w + ("." if p < 0.06 else "," if p < 0.10 else "!" if p < 0.11 else "")

    def doc(n):
        return " ".join(word() for _ in range(n))

    return doc


def run(case, size, seed):
    if type(size) is not int or type(seed) is not int or size < 1 or seed < 0:
        raise ValueError("size must be a positive int and seed a non-negative int")
    from nltk.sentiment.vader import SentimentIntensityAnalyzer

    sia = SentimentIntensityAnalyzer()
    if case == "transcripts":
        if size > 20000:
            raise ValueError("transcripts size is words per document, at most 20000")
        doc = _generator(sia, seed)
        docs = [doc(size) for _ in range(40)]
        return {"case": case, **_scores_record(sia, docs, keep_raw=size <= 200)}
    if case == "reviews":
        if size > 5000:
            raise ValueError("reviews size is the number of documents, at most 5000")
        doc = _generator(sia, seed)
        docs = [doc(120) for _ in range(size)]
        return {"case": case, **_scores_record(sia, docs, keep_raw=size <= 50)}
    if case == "edge":
        k = (size + seed) % len(EDGE)
        docs = EDGE[k:] + EDGE[:k]
        return {"case": case, **_scores_record(sia, docs, keep_raw=True)}
    raise ValueError("unsupported case")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
