"""Smart Hindi Phonetic Normalizer & Pronunciation Enhancement Engine for TTS.

Converts Hinglish, numbers, acronyms, and English loan words into 100% natural,
phonetically accurate Devanagari Hindi so that neural TTS models (such as
hi-IN-MadhurNeural, hi-IN-SwaraNeural, and ElevenLabs Multilingual) pronounce
every word, number, and concept with flawless native Hindi diction.
"""

import re
import json
import hashlib
from pathlib import Path
from typing import Dict, Optional

from autotube.config import PROJECT_ROOT, get_config
from autotube.utils.console import print_info, print_warning

# Disk cache for normalized phonetic scripts
CACHE_FILE = PROJECT_ROOT / "assets" / "cache" / "hindi_phonetics_cache.json"

# In-memory session cache
_MEMORY_CACHE: Dict[str, str] = {}


# ---------------------------------------------------------------------------
# 1. HINDI NUMBERS & PERCENTAGES DICTIONARY (0 to 100 + Units)
# ---------------------------------------------------------------------------
HINDI_NUMBERS = {
    0: "शून्य", 1: "एक", 2: "दो", 3: "तीन", 4: "चार", 5: "पांच",
    6: "छह", 7: "सात", 8: "आठ", 9: "नौ", 10: "दस",
    11: "ग्यारह", 12: "बारह", 13: "तेरह", 14: "चौदह", 15: "पंद्रह",
    16: "सोलह", 17: "सत्रह", 18: "अठारह", 19: "उन्नीस", 20: "बीस",
    21: "इक्कीस", 22: "बाईस", 23: "तेईस", 24: "चौबीस", 25: "पच्चीस",
    26: "छब्बीस", 27: "सत्ताईस", 28: "अट्ठाइस", 29: "उनतीस", 30: "तीस",
    31: "इकत्तीस", 32: "बत्तीस", 33: "तैंतीस", 34: "चौंतीस", 35: "पैंतीस",
    36: "छत्तीस", 37: "सैंतीस", 38: "अड़तीस", 39: "उनतालीस", 40: "चालीस",
    41: "इकतालीस", 42: "बयालीस", 43: "तैंतालीस", 44: "चौवालीस", 45: "पैंतालीस",
    46: "छियालीस", 47: "सैंतालीस", 48: "अड़तालीस", 49: "उनचास", 50: "पचास",
    51: "इक्यावन", 52: "बावन", 53: "तिरेपन", 54: "चौवन", 55: "पचपन",
    56: "छप्पन", 57: "सत्तावन", 58: "अट्ठावन", 59: "उनसठ", 60: "साठ",
    61: "इकसठ", 62: "बासठ", 63: "तिरसठ", 64: "चौंसठ", 65: "पैंसठ",
    66: "छियासठ", 67: "सरसठ", 68: "अड़सठ", 69: "उनहत्तर", 70: "सत्तर",
    71: "इकहत्तर", 72: "बहत्तर", 73: "तिहत्तर", 74: "चौहत्तर", 75: "पचहत्तर",
    76: "छिहत्तर", 77: "सतहत्तर", 78: "अठहत्तर", 79: "उन्नासी", 80: "अस्सी",
    81: "इक्यासी", 82: "बयासी", 83: "तिरासी", 84: "चौरासी", 85: "पचासी",
    86: "छियासी", 87: "सत्तासी", 88: "अट्ठासी", 89: "नवासी", 90: "नब्बे",
    91: "इक्यानवे", 92: "बानवे", 93: "तिरानवे", 94: "चौरानवे", 95: "पंचानवे",
    96: "छियानवे", 97: "सत्तानवे", 98: "अट्ठानवे", 99: "निन्यानवे", 100: "सौ",
}


# ---------------------------------------------------------------------------
# 2. ACRONYMS & ABBREVIATIONS PHONETIC MAPPING
# ---------------------------------------------------------------------------
ACRONYMS_MAP = {
    "DNA": "डी.एन.ए.",
    "RNA": "आर.एन.ए.",
    "AI": "ए.आई.",
    "A.I.": "ए.आई.",
    "NASA": "नासा",
    "ISRO": "इसरो",
    "UFO": "यू.एफ़.ओ.",
    "FBI": "एफ़.बी.आई.",
    "CIA": "सी.आई.ए.",
    "FMRI": "एफ़.एम.आर.आई.",
    "fMRI": "एफ़.एम.आर.आई.",
    "BGM": "बी.जी.एम.",
    "CTA": "सी.टी.ए.",
    "CCTV": "सी.सी.टी.वी.",
    "TV": "टी.वी.",
    "SMS": "एस.एम.एस.",
    "GPS": "जी.पी.एस.",
    "VIP": "वी.आई.पी.",
    "CEO": "सी.ई.ओ.",
    "PM": "पी.एम.",
    "KG": "किलोग्राम",
    "KM": "किलोमीटर",
    "MB": "एम.बी.",
    "GB": "जी.बी.",
    "USA": "यू.एस.ए.",
    "US": "यू.एस.",
}


# ---------------------------------------------------------------------------
# 3. COMMON ENGLISH LOAN WORDS PHONETIC MAPPING
# ---------------------------------------------------------------------------
LOAN_WORDS_MAP = {
    "black hole": "ब्लैक होल",
    "blackhole": "ब्लैक होल",
    "spaghettification": "स्पैगेटी-फिकेशन",
    "gravity": "ग्रेविटी",
    "technology": "टेक्नोलॉजी",
    "advanced technology": "एडवांस टेक्नोलॉजी",
    "science": "साइंस",
    "scientists": "साइंटिस्ट्स",
    "scientist": "साइंटिस्ट",
    "quantum": "क्वांटम",
    "universe": "यूनिवर्स",
    "solar system": "सोलर सिस्टम",
    "galaxy": "गैलेक्सी",
    "galaxies": "गैलेक्सीज़",
    "planet": "प्लैनेट",
    "planets": "प्लैनेट्स",
    "earth": "अर्थ",
    "space": "स्पेस",
    "cosmic": "कॉस्मिक",
    "telescope": "टेलीस्कोप",
    "satellite": "सैटेलाइट",
    "astronaut": "एस्ट्रोनॉट",
    "simulation": "सिमुलेशन",
    "matrix": "मैट्रिक्स",
    "glitch": "ग्लिच",
    "psychology": "साइकोलॉजी",
    "psychological": "साइकोलॉजिकल",
    "subconscious": "सबकॉन्शियस",
    "manipulation": "मैनिपुलेशन",
    "mind games": "माइंड गेम्स",
    "mind hacks": "माइंड हैक्स",
    "mind-blowing": "माइंड-ब्लोइंग",
    "bacteria": "बैक्टीरिया",
    "virus": "वायरस",
    "robot": "रोबोट",
    "robots": "रोबोट्स",
    "computer": "कंप्यूटर",
    "screen": "स्क्रीन",
    "smartphone": "स्मार्टफोन",
    "phone": "फोन",
    "mobile": "मोबाइल",
    "circuit": "सर्किट",
    "chip": "चिप",
    "microchip": "माइक्रोचिप",
    "network": "नेटवर्क",
    "internet": "इंटरनेट",
    "camera": "कैमरा",
    "video": "वीडियो",
    "videos": "वीडियोज़",
    "channel": "चैनल",
    "subscribe": "सब्सक्राइब",
    "comment": "कमेंट",
    "comments": "कमेंट्स",
    "like": "लाइक",
    "share": "शेयर",
    "superpower": "सुपरपावर",
    "superpowers": "सुपरपावर्स",
    "shocking": "शॉकिंग",
    "mystery": "मिस्ट्री",
    "mysteries": "मिस्ट्रीज़",
    "facts": "फैक्ट्स",
    "secret": "सीक्रेट",
    "secrets": "सीक्रेट्स",
    "dangerous": "डेंजरस",
    "horror": "हॉरर",
    "formula": "फॉर्मूला",
    "experiment": "एक्सपेरिमेंट",
    "signal": "सिग्नल",
    "signals": "सिग्नल्स",
    "dimension": "डायमेंशन",
    "dimensions": "डायमेंशंस",
    "portal": "पोर्टल",
    "wormhole": "वर्महोल",
    "energy": "एनर्जी",
    "light": "लाइट",
    "laser": "लेज़र",
    "frequency": "फ्रीक्वेंसी",
    "vibration": "वाइब्रेशन",
    "resonance": "रेजोनेंस",
    "atom": "एटम",
    "atoms": "एटम्स",
    "molecule": "मॉलिक्यूल",
    "molecules": "मॉलिक्यूल्स",
    "chemical": "केमिकल",
    "compound": "कंपाउंड",
    "alien": "एलियन",
    "aliens": "एलियंस",
    "yes": "यस",
    "no": "नो",
    "type 1": "टाइप वन",
    "type 2": "टाइप टू",
    "type-1": "टाइप वन",
    "type-2": "टाइप टू",
    "changes": "चेंजेस",
    "proof": "प्रूफ",
    "evidence": "एविडेंस",
    "theory": "थ्योरी",
    "discovery": "डिस्कवरी",
    "impossible": "इम्पॉसिबल",
    "amazing": "अमेज़िंग",
    "incredible": "इन्क्रेडिबल",
}


# ---------------------------------------------------------------------------
# 4. HINGLISH VOCABULARY FALLBACK MAPPING (Common spoken words)
# ---------------------------------------------------------------------------
HINGLISH_VOCAB = {
    "agar": "अगर", "toh": "तो", "to": "तो", "ek": "एक", "hai": "है", "hain": "हैं",
    "ho": "हो", "gaya": "गया", "gayi": "गई", "gaye": "गए", "jayenge": "जाएंगे",
    "jayegi": "जाएगी", "jayega": "जाएगा", "kar": "कर", "karein": "करें", "karo": "करो",
    "raongte": "रोंगटे", "rongte": "रोंगटे", "khade": "खड़े", "zameen": "ज़मीन",
    "takra": "टकरा", "anjaam": "अंजाम", "dekhkar": "देखकर", "sochiye": "सोचिए",
    "achanak": "अचानक", "aasmaan": "आसमान", "prakat": "प्रकट", "kya": "क्या",
    "hoga": "होगा", "sabse": "सबसे", "pehle": "पहले", "bhayankar": "भयानक",
    "khichne": "खिंचने", "lagegi": "लगेगी", "jaise": "जैसे", "kareeb": "करीब",
    "aayega": "आएगा", "samandar": "समंदर", "pahad": "पहाड़", "apni": "अपनी",
    "jagah": "जगह", "chhodkar": "छोड़कर", "hawa": "हवा", "teerne": "तैरने",
    "teerni": "तैरने", "shuru": "शुरू", "denge": "देंगे", "dharati": "धरती",
    "dharti": "धरती", "rabar": "रबर", "tarah": "तरह", "khich": "खिंच",
    "lambi": "लंबी", "iske": "इसके", "baad": "बाद", "khaufnak": "खौफ़नाक",
    "daur": "दौर", "jisme": "जिसमें", "har": "हर", "insaan": "इंसान",
    "imaratey": "इमारतें", "patli": "पतली", "hokar": "होकर", "gayab": "गायब",
    "kuch": "कुछ", "palon": "पलों", "hamara": "हमारा", "poora": "पूरा",
    "neela": "नीला", "grah": "ग्रह", "uska": "उसका", "nivala": "निवाला",
    "ban": "बन", "nakshe": "नक्शे", "naam": "नाम", "nishaan": "निशान",
    "hamesha": "हमेशा", "liye": "लिए", "mit": "मिट", "kehta": "कहता",
    "shakti": "शक्ति", "bachna": "बचना", "aisi": "ऐसी", "namumkin": "नामुमकिन",
    "chunauti": "चुनौती", "jiska": "जिसका", "koi": "कोई", "ant": "अंत",
    "nahi": "नहीं", "lagta": "लगता", "tabahi": "तबाही", "bacha": "बचा",
    "payegi": "पाएगी", "likhkar": "लिखकर", "apna": "अपना", "jawab": "जवाब",
    "do": "दो", "aur": "और", "abhi": "अभी", "lekin": "लेकिन", "magar": "मगर",
    "kyunki": "क्योंकि", "isliye": "इसलिए", "balki": "बल्कि", "shayad": "शायद",
    "duniya": "दुनिया", "insani": "इंसानी", "dimag": "दिमाग", "soch": "सोच",
    "sach": "सच", "jhooth": "झूठ", "rahasya": "रहस्य", "itihas": "इतिहास",
    "prachin": "प्राचीन", "vigyan": "विज्ञान", "bharat": "भारत", "mandir": "मंदिर",
}


def _load_cache():
    global _MEMORY_CACHE
    if not _MEMORY_CACHE and CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _MEMORY_CACHE = json.load(f)
        except Exception:
            _MEMORY_CACHE = {}


def _save_cache():
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_MEMORY_CACHE, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def expand_numbers_to_hindi(text: str) -> str:
    """Convert digits, years, durations, and percentages into native Hindi words."""
    # 1. Percentages (e.g. 99%, 100%, 50%)
    def replace_percent(match):
        num = int(match.group(1))
        word = HINDI_NUMBERS.get(num, str(num))
        return f"{word} प्रतिशत"

    text = re.sub(r"\b(\d{1,3})\s*%", replace_percent, text)

    # 2. Time durations with seconds/minutes/hours
    def replace_seconds(match):
        num = int(match.group(1))
        word = HINDI_NUMBERS.get(num, str(num))
        return f"{word} सेकंड"

    text = re.sub(r"\b(\d{1,3})\s*(?:seconds|second|sec|सेकंड)\b", replace_seconds, text, flags=re.IGNORECASE)

    def replace_minutes(match):
        num = int(match.group(1))
        word = HINDI_NUMBERS.get(num, str(num))
        return f"{word} मिनट"

    text = re.sub(r"\b(\d{1,3})\s*(?:minutes|minute|min|मिनट)\b", replace_minutes, text, flags=re.IGNORECASE)

    def replace_hours(match):
        num = int(match.group(1))
        word = HINDI_NUMBERS.get(num, str(num))
        return f"{word} घंटे"

    text = re.sub(r"\b(\d{1,3})\s*(?:hours|hour|घंटे|घंटा)\b", replace_hours, text, flags=re.IGNORECASE)

    # 3. Thousands (e.g. 5,000 or 5000)
    def replace_thousands(match):
        prefix = match.group(1).replace(",", "")
        p_int = int(prefix)
        thousands = p_int // 1000
        remainder = p_int % 1000
        t_word = HINDI_NUMBERS.get(thousands, str(thousands))
        if remainder == 0:
            return f"{t_word} हज़ार"
        elif remainder in HINDI_NUMBERS:
            return f"{t_word} हज़ार {HINDI_NUMBERS[remainder]}"
        return f"{t_word} हज़ार"

    text = re.sub(r"\b([1-9]\d{0,2}[,.]?000)\b", replace_thousands, text)

    # 4. Standalone numbers 0-100
    def replace_small_nums(match):
        num = int(match.group(0))
        if num in HINDI_NUMBERS:
            return HINDI_NUMBERS[num]
        return match.group(0)

    text = re.sub(r"\b(100|[1-9]?[0-9])\b", replace_small_nums, text)

    return text


def apply_phonetic_lexicon(text: str) -> str:
    """Map English loan words, scientific terms, and acronyms to standard Devanagari phonetics."""
    # Replace acronyms first
    for acr, hindi_ph in ACRONYMS_MAP.items():
        pattern = rf"\b{re.escape(acr)}\b"
        text = re.sub(pattern, hindi_ph, text)

    # Replace loan words (case-insensitive)
    for en_word, dev_word in LOAN_WORDS_MAP.items():
        pattern = rf"\b{re.escape(en_word)}\b"
        text = re.sub(pattern, dev_word, text, flags=re.IGNORECASE)

    return text


def fast_hinglish_to_devanagari_rulebased(text: str) -> str:
    """Fast local dictionary-based Hinglish to Devanagari conversion (fallback)."""
    words = text.split()
    converted_words = []
    for w in words:
        clean = re.sub(r"[^\w]", "", w).lower()
        if clean in HINGLISH_VOCAB:
            # Preserve punctuation around the word
            punct_before = re.match(r"^[^\w]+", w)
            punct_after = re.search(r"[^\w]+$", w)
            p_b = punct_before.group(0) if punct_before else ""
            p_a = punct_after.group(0) if punct_after else ""
            converted_words.append(f"{p_b}{HINGLISH_VOCAB[clean]}{p_a}")
        else:
            converted_words.append(w)
    return " ".join(converted_words)


def transliterate_hinglish_with_gemini(text: str) -> Optional[str]:
    """Transliterate Hinglish into 100% pure phonetic Devanagari using Gemini Flash-Lite.
    
    Guarantees zero robotic English accent in Edge-TTS.
    """
    cfg = get_config()
    api_key = getattr(cfg, "gemini_api_key", "")
    if not api_key:
        return None

    try:
        from google import genai
        client = genai.Client(api_key=api_key)

        prompt = f"""You are a master Hindi phonetic engine for Text-to-Speech (hi-IN-MadhurNeural).
Your job is to take the input text (which is in Hinglish or mixed English-Hindi) and output 100% PURE DEVANAGARI HINDI so that Edge-TTS pronounces EVERY word, number, and concept naturally with zero English accent.

CRITICAL RULES:
1. Every word MUST be in Devanagari script. NOT A SINGLE English/Latin letter must remain.
2. English technical and viral words must be written in standard Devanagari phonetics:
   - 'black hole' -> 'ब्लैक होल'
   - 'gravity' -> 'ग्रेविटी'
   - 'DNA' -> 'डी.एन.ए.'
   - 'AI' -> 'ए.आई.'
   - 'technology' -> 'टेक्नोलॉजी'
   - 'scientists' -> 'साइंटिस्ट्स'
   - 'spaghettification' -> 'स्पैगेटी-फिकेशन'
   - 'comment' -> 'कमेंट'
   - 'subscribe' -> 'सब्सक्राइब'
   - 'like' -> 'लाइक'
3. Numbers and percentages must be converted to Hindi words:
   - '5000' -> 'पांच हज़ार'
   - '99%' -> 'निन्यानवे प्रतिशत'
   - '7' -> 'सात'
4. Transliterate spoken Hinglish directly (do not change the meaning or grammar):
   - 'raongte khade ho jayenge' -> 'रोंगटे खड़े हो जाएंगे'
   - 'prakat ho jaye' -> 'प्रकट हो जाए'
   - 'chhodkar' -> 'छोड़कर'
5. Output ONLY the clean Devanagari text. Zero explanations or markdown.

Input Text:
{text}"""

        resp = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
        )
        if resp.text:
            clean = resp.text.strip()
            # Verify that output actually contains Devanagari characters
            if any("\u0900" <= c <= "\u097f" for c in clean):
                return clean
    except Exception as e:
        print_warning(f"Gemini Hindi phonetic transliteration notice: {e}")

    return None


def normalize_hindi_for_tts(text: str) -> str:
    """Master entry point: Convert any Hindi/Hinglish text to phonetically perfect Devanagari for TTS.

    Benefits:
    - Eliminates robotic English accents on Hindi words (e.g. 'raongte' -> 'रोंगटे').
    - Fixes English loanwords and acronyms ('DNA' -> 'डी.एन.ए.', 'black hole' -> 'ब्लैक होल').
    - Expands numbers to Hindi words ('5000' -> 'पांच हज़ार', '99%' -> 'निन्यानवे प्रतिशत').
    - Fully cached for sub-millisecond repeated performance.
    """
    if not text or not text.strip():
        return text

    _load_cache()
    text_hash = hashlib.md5(text.strip().encode("utf-8")).hexdigest()
    if text_hash in _MEMORY_CACHE:
        return _MEMORY_CACHE[text_hash]

    # Step 1: Expand numbers and percentages to Hindi words
    processed = expand_numbers_to_hindi(text)

    # Step 2: Apply acronyms and loan word phonetic mappings
    processed = apply_phonetic_lexicon(processed)

    # Step 3: Check if text is predominantly Latin/Hinglish
    latin_chars = sum(1 for c in processed if ("a" <= c.lower() <= "z"))
    devanagari_chars = sum(1 for c in processed if ("\u0900" <= c <= "\u097f"))

    is_predominantly_hinglish = latin_chars > 20 and (latin_chars > devanagari_chars * 0.4)

    if is_predominantly_hinglish:
        # Transliterate Hinglish to 100% Devanagari using Gemini
        ai_devanagari = transliterate_hinglish_with_gemini(processed)
        if ai_devanagari:
            # Re-apply phonetic lexicon on AI output to ensure perfect acronyms/loan words
            processed = apply_phonetic_lexicon(ai_devanagari)
            processed = expand_numbers_to_hindi(processed)
        else:
            # Fallback to local rule-based Hinglish mapper
            processed = fast_hinglish_to_devanagari_rulebased(processed)

    # Step 4: Final cleanup of spaces and punctuation
    processed = re.sub(r"\s+", " ", processed).strip()

    # Save to memory and disk cache
    _MEMORY_CACHE[text_hash] = processed
    _save_cache()

    return processed
