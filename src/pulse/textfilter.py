"""Text-level filters applied in the scrub stage: emoji removal, English check, word count."""

import re
import unicodedata

WHITESPACE = re.compile(r"\s+")

EMOJI = re.compile(
    "["
    "\U0001f000-\U0001faff"  # pictographs, emoticons, transport, flags, symbols
    "☀-➿"  # misc symbols and dingbats (✅ ❤ ✨ ❌ ✔)
    "⌀-⏿"  # misc technical (⌚ ⏰)
    "⬀-⯿"  # arrows and stars (⭐ ⬆)
    "▪-◾⤴⤵〰〽㊗㊙‼⁉™ℹⓂ©®"
    "️‍⃣"  # variation selector, ZWJ, keycap
    "]+"
)

WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")

ENGLISH_WORDS = frozenset(
    """a an the and or but if so then than that this these those it its it's i me my we our
    you your he she they them their is am are was were be been being do does did done have has had
    to of in on at for with from by as about into out up down over not no yes can could will would
    should may might must just very too also all any some more most much many what which who when
    where why how there here only even still again after before while because when ever never
    again get got getting use using used app good bad best worst please other others""".split()
)

HINGLISH_WORDS = frozenset(
    """hai hain hota hoti hote ho tha thi nahi nahin nhi kya kyun kyu kaise kab kahan kuch koi
    mera meri mere hamara apna apni aap aapka tum tumhara ye yeh wo woh isliye liye lekin par
    magar aur ya ki ke ka ko se mein pe pr  bahut bohot bhut accha acha achha bekar bakwas
    paisa paise kar karo karna kiya kiye kare karta karte raha rahe rahi gaya gaye gayi
    hua hue hui abhi bilkul sirf sab sabhi bhi toh tha thoda jyada zyada wala wali
    nahi mat chahiye milta milega mila""".split()
)

ENGLISH_MIN_SHARE = 0.15
HINGLISH_MAX_SHARE = 0.12
NON_LATIN_MAX_SHARE = 0.1


def strip_emoji(text: str) -> str:
    """Remove emoji and collapse the whitespace they leave behind."""
    return WHITESPACE.sub(" ", EMOJI.sub(" ", text)).strip()


def words(text: str) -> list[str]:
    return WORD.findall(text)


def word_count(text: str) -> int:
    """The one shared counter (CMP-7): a word is a run of letters or digits, with inner
    apostrophes. Punctuation, bullets, dashes, ★ and Markdown marks count as nothing; "4.2",
    "F&O" and "1,596" count as two words each, so the count errs high, never low."""
    return len(words(text))


def is_english(text: str) -> bool:
    """Heuristic: mostly Latin script, English function words present, Hinglish markers absent.

    Hindi and other scripts fail the script check. Romanised Hindi is caught by marker words;
    other Latin-script languages fail the English function-word share.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    non_latin = sum(1 for ch in letters if not unicodedata.name(ch, "").startswith("LATIN"))
    if non_latin / len(letters) > NON_LATIN_MAX_SHARE:
        return False
    tokens = [w.casefold() for w in words(text)]
    if not tokens:
        return False
    english = sum(t in ENGLISH_WORDS for t in tokens) / len(tokens)
    hinglish = sum(t in HINGLISH_WORDS for t in tokens) / len(tokens)
    return english >= ENGLISH_MIN_SHARE and hinglish < HINGLISH_MAX_SHARE
