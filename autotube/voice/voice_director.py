"""Subject-aware voice selection for AutoTube narration."""


SPACE_KEYS = (
    "black hole", "blackhole", "space", "antariksh", "brahmand", "galaxy",
    "universe", "cosmos", "planet", "solar system", "astronomy", "astronaut",
    "rocket", "moon", "mars", "sun", "nebula", "supernova", "gravity",
    "event horizon", "singularity", "spaghettification", "time dilation",
)
SCIENCE_KEYS = (
    "science", "scientific", "physics", "chemistry", "biology", "experiment",
    "quantum", "atom", "ai", "artificial intelligence", "technology",
    "machine learning", "robot", "brain", "neuron", "psychology",
)
HISTORY_KEYS = (
    "history", "historical", "ancient", "medieval", "empire", "war", "battle",
    "mahabharat", "ramayan", "mughal", "ashoka", "gandhi", "bose", "netaji",
    "independence", "archaeology", "temple", "civilization",
)
MYSTERY_KEYS = (
    "mystery", "mysterious", "unsolved", "secret", "hidden", "unknown",
    "paranormal", "ghost", "haunted", "conspiracy", "alien", "ufo",
    "bermuda", "roswell", "strange", "unexplained", "real incident",
    "true crime", "crime", "case",
)
EMOTIONAL_KEYS = (
    "emotional", "love", "heartbreaking", "survivor", "inspiring", "inspiration",
    "life story", "tragedy", "family", "childhood",
)
TECH_KEYS = (
    "coding", "software", "programming", "computer", "startup", "app",
    "database", "cloud", "cyber", "internet", "iphone", "android",
)
VIRAL_KEYS = (
    "facts", "fact", "did you know", "amazing", "mind blowing", "viral",
    "shorts", "quick facts", "top", "list",
)


VOICE_RULES: dict[str, dict[str, str]] = {
    "hi": {
        "space": "hi_deep_cinematic_male",
        "science": "hi_calm_male",
        "history": "hi_authoritative_male",
        "mystery": "hi_cinematic_male",
        "emotional": "hi_cinematic_female",
        "technology": "hi_young_male",
        "viral": "hi_young_male",
        "default": "hi_authoritative_male",
    },
    "en": {
        "space": "en_deep_cinematic_male",
        "science": "en_calm_british_male",
        "history": "en_deep_british_male",
        "mystery": "en_cinematic_narrator",
        "emotional": "en_cinematic_female",
        "technology": "en_authoritative_male",
        "viral": "en_cinematic_narrator",
        "default": "en_authoritative_male",
    },
}


def _has_any(text: str, keys: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(key in lowered for key in keys)


def detect_language(text: str, requested: str = "hi") -> str:
    """Return hi/en using explicit request first, then script content."""
    req = (requested or "").lower().strip()
    if req in {"hi", "hindi", "hinglish", "hi-en"}:
        return "hi"
    if req in {"en", "english"}:
        return "en"
    devanagari = sum("\u0900" <= ch <= "\u097f" for ch in text)
    latin = sum(("a" <= ch.lower() <= "z") for ch in text)
    return "hi" if devanagari >= max(5, latin * 0.25) else "en"


def choose_subject_voice(title: str, script_text: str, language: str = "hi") -> str:
    """Select the best catalog voice for the topic while keeping gender consistent."""
    lang = detect_language(f"{title}\n{script_text}", language)
    text = f"{title} {script_text}".lower()

    if _has_any(text, SPACE_KEYS):
        category = "space"
    elif _has_any(text, HISTORY_KEYS):
        category = "history"
    elif _has_any(text, MYSTERY_KEYS):
        category = "mystery"
    elif _has_any(text, TECH_KEYS):
        category = "technology"
    elif _has_any(text, SCIENCE_KEYS):
        category = "science"
    elif _has_any(text, EMOTIONAL_KEYS):
        category = "emotional"
    elif _has_any(text, VIRAL_KEYS):
        category = "viral"
    else:
        category = "default"

    return VOICE_RULES[lang][category]


def resolve_voice_for_content(
    configured_voice: str | None,
    title: str,
    script_text: str,
    language: str,
) -> str:
    """Resolve automatic or incompatible voices from the complete narration context."""
    requested = (configured_voice or "").strip()
    if requested.lower() in {"", "auto", "automatic", "smart", "default"}:
        return choose_subject_voice(title=title, script_text=script_text, language=language)
    if not is_voice_language_compatible(requested, language):
        return choose_subject_voice(title=title, script_text=script_text, language=language)
    return requested


def is_voice_language_compatible(voice_id: str, language: str) -> bool:
    """Check catalog-style voice IDs without importing catalog data."""
    key = (voice_id or "").lower()
    lang = detect_language("", language)
    if lang == "hi":
        return key.startswith("hi_") or key in {"madhur", "swara", "akashvani"}
    return key.startswith("en_") or key in {
        "adam", "christopher", "guy", "aria", "andrew", "ryan", "en",
    }


def voice_family(voice_id: str) -> str:
    key = (voice_id or "").lower()
    if "female" in key or key in {"swara", "aria"}:
        return "female"
    return "male"
