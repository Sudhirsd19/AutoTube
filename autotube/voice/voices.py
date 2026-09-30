"""Voice catalog and presets for Edge-TTS."""

from typing import Dict, List
from pydantic import BaseModel


class VoiceProfile(BaseModel):
    id: str
    name: str
    gender: str
    language: str
    description: str


VOICE_CATALOG: Dict[str, VoiceProfile] = {
    # Most Popular Viral Voices (YouTube Shorts, Reels, Documentaries)
    "adam": VoiceProfile(
        id="en-US-ChristopherNeural",
        name="Adam",
        gender="Male",
        language="en-US",
        description="#1 Most popular viral narrator voice on YouTube Shorts & TikTok (ElevenLabs Adam / Edge-TTS Christopher)",
    ),
    "madhur": VoiceProfile(
        id="hi-IN-MadhurNeural",
        name="Madhur",
        gender="Male",
        language="hi-IN",
        description="Most widely used Hindi narrator voice for YouTube Shorts and documentary channels",
    ),
    # English (US)
    "christopher": VoiceProfile(
        id="en-US-ChristopherNeural",
        name="Christopher",
        gender="Male",
        language="en-US",
        description="Deep, authoritative, documentary narrator style (Recommended for faceless channels)",
    ),
    "guy": VoiceProfile(
        id="en-US-GuyNeural",
        name="Guy",
        gender="Male",
        language="en-US",
        description="Conversational, energetic storyteller, great for viral Shorts",
    ),
    "aria": VoiceProfile(
        id="en-US-AriaNeural",
        name="Aria",
        gender="Female",
        language="en-US",
        description="Warm, clear, and professional female voice",
    ),
    "andrew": VoiceProfile(
        id="en-US-AndrewNeural",
        name="Andrew",
        gender="Male",
        language="en-US",
        description="Young, dynamic, tech-oriented voice",
    ),
    "baby": VoiceProfile(
        id="en-US-AnaNeural",
        name="Baby",
        gender="Female",
        language="en-US",
        description="Cute, playful baby/child cartoon voice (Baby Groot style)",
    ),
    "ana": VoiceProfile(
        id="en-US-AnaNeural",
        name="Ana",
        gender="Female",
        language="en-US",
        description="Cute young child voice",
    ),
    # Hindi / Hinglish
    "madhur": VoiceProfile(
        id="hi-IN-MadhurNeural",
        name="Madhur",
        gender="Male",
        language="hi-IN",
        description="Deep, rich Indian male voice (Ideal for Hindi facts/documentaries)",
    ),
    "swara": VoiceProfile(
        id="hi-IN-SwaraNeural",
        name="Swara",
        gender="Female",
        language="hi-IN",
        description="Crisp, expressive Indian female voice",
    ),
    # English (UK)
    "ryan": VoiceProfile(
        id="en-GB-RyanNeural",
        name="Ryan",
        gender="Male",
        language="en-GB",
        description="Refined British male narrator",
    ),
    "sonia": VoiceProfile(
        id="en-GB-SoniaNeural",
        name="Sonia",
        gender="Female",
        language="en-GB",
        description="Classic British documentary female voice",
    ),
}


def get_voice_id(name_or_id: str) -> str:
    """Resolve a friendly voice name or direct ID to the full Edge-TTS voice identifier."""
    key = name_or_id.lower().strip()
    if key in VOICE_CATALOG:
        return VOICE_CATALOG[key].id
    # If passed as direct voice id e.g. 'en-US-GuyNeural'
    return name_or_id


def list_available_voices() -> List[VoiceProfile]:
    return list(VOICE_CATALOG.values())
