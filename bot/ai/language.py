import re

DEVANAGARI = re.compile(r"[\u0900-\u097F]")

HINGLISH_WORDS = set(
    """
    kya kaise kyun kyunki kaisa kaun kab kahan nahi nahin nhi tum aap tumhara tumhari
    mera meri mujhe tumhe acha accha achha theek thik theek hai kar karo karta karti
    karke kare raha rahi ho hain hai tha thi the yaar bhai behen dost dil pyaar ghar
    khana paani pani matlab chal chalo batao suno namaste dhanyavad bahut thoda abhi
    aaj kal par nai haan ji re se ke liye mujhko tumhara hamara apna apni wala wali
    hota hoti hojaayega kardo karta kro plz please bta do bata na sun na chup karo
    """.split()
)


def detect(text: str) -> str:
    """Return 'hi' for Hindi/Hinglish, 'en' for English."""
    t = (text or "").lower()
    if DEVANAGARI.search(t):
        return "hi"
    words = re.findall(r"[a-z']+", t)
    if not words:
        return "en"
    hits = sum(1 for w in words if w in HINGLISH_WORDS)
    if hits >= 2:
        return "hi"
    if hits == 1 and len(words) <= 4:
        return "hi"
    return "en"
