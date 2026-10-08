"""Protected native regression for nltk-3638-vader-index (authored wrapper, upstream assertions).

Runs the upstream "Vader" section of nltk/test/sentiment.doctest (byte-pinned copy from the
reference commit, staged next to this file) verbatim. The only stand-in: the section calls
nltk.tokenize.sent_tokenize on one paragraph, which needs the punkt_tab model (not shipped in
the images); it is replaced by a regex split on sentence-final punctuation that yields exactly
the nine sentences the doctest expects. Every expected score line is upstream text.
"""
import doctest
from pathlib import Path
import re

DOCTEST = Path(__file__).with_name("sentiment.doctest")


def _regex_sent_tokenize(text, language="english"):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def test_vader_doctest_section(monkeypatch):
    import nltk.tokenize

    monkeypatch.setattr(nltk.tokenize, "sent_tokenize", _regex_sent_tokenize)
    text = DOCTEST.read_text(encoding="utf-8")
    section = text[text.index("\nVader\n"):]
    test = doctest.DocTestParser().get_doctest(section, {}, "sentiment.doctest[Vader]", str(DOCTEST), 0)
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
    report = []
    runner.run(test, out=report.append)
    failed, attempted = runner.summarize(verbose=False)
    assert attempted >= 9, attempted
    assert failed == 0, "".join(report)
