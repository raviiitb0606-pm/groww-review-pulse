import pytest

from pulse.pii import detect, scrub, scrub_with_stats

POSITIVE = [
    ("mail me at rahul.k99@gmail.com please", "email"),
    ("see https://groww.in/p/abc?x=1 for proof", "url"),
    ("pay to rahul@okhdfcbank now", "upi"),
    ("my pan ABCDE1234F is stuck", "pan"),
    ("ref no 8837261 not resolved", "reference"),
    ("order id: ORD12345678 failed", "reference"),
    ("ticket number 28105753 check", "reference"),
    ("aadhaar 1234 5678 9012 rejected", "aadhaar"),
    ("aadhaar 123456789012 rejected", "aadhaar"),
    ("call 9876543210 back", "phone"),
    ("call +91 98765 43210 back", "phone"),
    ("call +919876543210 back", "phone"),
    ("call 098765-43210 back", "phone"),
    ("call 98765-43210 back", "phone"),
    ("account 123456789012345 debited", "digits"),
    ("Hi Rahul, my money is stuck", "name"),
    ("thanks and regards, Priya Sharma", "name"),
]

NEGATIVE = [
    "I lost ₹10,000 in one day",
    "returns of 12.5% in 2024",
    "it took 12 digit verification",
    "version 18.22.1 keeps crashing",
    "Hi Groww, please fix the app",
    "Thanks Team for the quick help",
    "Dear Sir, kindly resolve this",
    "waited 45 minutes and 3 calls",
    "rated 5 stars out of 5",
    "mutual fund of 1,00,000 rupees",
    "thanks India market is fine",
    "Hey Grow & Team why no average",
    "the best platform for beginners",
    "Hi, Don't trust this broker",
]


@pytest.mark.parametrize(("text", "kind"), POSITIVE)
def test_detects_and_scrubs(text, kind):
    assert kind in detect(text)
    assert detect(scrub(text)) == []


@pytest.mark.parametrize("text", NEGATIVE)
def test_ordinary_text_survives(text):
    assert detect(text) == []
    assert scrub(text) == text


def test_redaction_share_counts_changed_chars():
    s = scrub_with_stats("9876543210")
    assert s.text == "[redacted]" and s.redacted_chars == 10
