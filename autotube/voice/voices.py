"""Voice catalog and presets for Edge-TTS with specialized cinematic, space, mystery, and science profiles."""

from typing import Dict, List, Optional
from pydantic import BaseModel


class VoiceProfile(BaseModel):
    id: str                # Internal unique slug (e.g. 'hi_deep_cinematic_male')
    edge_voice_id: str     # Raw Edge-TTS neural voice (e.g. 'hi-IN-MadhurNeural')
    name: str              # Friendly UI display name
    gender: str            # 'Male' | 'Female'
    language: str          # 'Hindi' | 'English'
    description: str
    best_for: str          # Channel use-case tag
    rate: str = "-8%"      # Default speed (0.90x - 0.95x)
    pitch: str = "-10Hz"   # Sub-bass pitch shift
    audio_filter: str = "" # FFmpeg filter for deep cinematic warmth, presence, or subtle reverb


VOICE_CATALOG: Dict[str, VoiceProfile] = {
    # =========================================================================
    # 🇮🇳 HINDI VOICES — SPACE / MYSTERY / SCIENCE
    # =========================================================================
    "hi_deep_cinematic_male": VoiceProfile(
        id="hi_deep_cinematic_male",
        edge_voice_id="hi-IN-MadhurNeural",
        name="🎙️ Deep Cinematic Male Hindi (Space, Universe, Black Holes) ⭐ BEST",
        gender="Male",
        language="Hindi",
        description="Deep, resonant, low-bass cinematic voice. Perfect for Black Holes, Cosmic Event Horizons, and Space Mysteries.",
        best_for="Space, Universe, Black Holes, Time Travel",
        rate="-8%",   # 0.92x speed
        pitch="-14Hz", # Deep sub-bass resonance
        audio_filter="equalizer=f=110:width_type=o:width=1.5:g=4.5,equalizer=f=3200:width_type=o:width=1.2:g=2.0,acompressor=threshold=-18dB:ratio=2.5:attack=10:release=120",
    ),
    "hi_calm_male": VoiceProfile(
        id="hi_calm_male",
        edge_voice_id="hi-IN-MadhurNeural",
        name="🎙️ Calm Male Hindi (Science Explanations, Astronomy, Planet Facts)",
        gender="Male",
        language="Hindi",
        description="Intellectual, calm, clear storytelling pace. Perfect for scientific explanations and astronomy facts.",
        best_for="Science explanations, Astronomy, Planet facts",
        rate="-6%",   # 0.94x speed
        pitch="-4Hz",
        audio_filter="equalizer=f=180:width_type=o:width=1.2:g=2.0,equalizer=f=3500:width_type=o:width=1.0:g=1.5",
    ),
    "hi_cinematic_male": VoiceProfile(
        id="hi_cinematic_male",
        edge_voice_id="hi-IN-MadhurNeural",
        name="🎙️ Cinematic Male Hindi (Mystery, रहस्य, Unsolved Stories)",
        gender="Male",
        language="Hindi",
        description="Dark, suspenseful, thrilling narration with subtle atmospheric depth for unexplained phenomena.",
        best_for="Mystery, रहस्य, Unsolved Stories",
        rate="-9%",   # 0.91x speed
        pitch="-10Hz",
        audio_filter="equalizer=f=120:width_type=o:width=1.4:g=3.5,equalizer=f=2800:width_type=o:width=1.2:g=2.0,aecho=0.8:0.4:80:0.15",
    ),
    "hi_authoritative_male": VoiceProfile(
        id="hi_authoritative_male",
        edge_voice_id="hi-IN-MadhurNeural",
        name="🎙️ Authoritative Male Hindi (History, Science Facts, Educational)",
        gender="Male",
        language="Hindi",
        description="Commanding, historical documentary presence with crisp articulation and educational authority.",
        best_for="History, Science Facts, Educational Videos",
        rate="-6%",   # 0.94x speed
        pitch="-7Hz",
        audio_filter="equalizer=f=140:width_type=o:width=1.5:g=3.0,equalizer=f=4000:width_type=o:width=1.0:g=2.5",
    ),
    "hi_young_male": VoiceProfile(
        id="hi_young_male",
        edge_voice_id="hi-IN-MadhurNeural",
        name="🎙️ Young Male Hindi (YouTube Shorts, Fast Facts, Viral Content)",
        gender="Male",
        language="Hindi",
        description="Energetic, fast-paced, high retention delivery for quick Shorts and viral hooks.",
        best_for="YouTube Shorts, Fast Facts, Viral Content",
        rate="+2%",   # 1.02x speed
        pitch="+0Hz",
        audio_filter="equalizer=f=2500:width_type=o:width=1.0:g=2.5",
    ),
    "hi_deep_female": VoiceProfile(
        id="hi_deep_female",
        edge_voice_id="hi-IN-SwaraNeural",
        name="🎙️ Deep Female Hindi (Mystery, Paranormal, Dark Stories)",
        gender="Female",
        language="Hindi",
        description="Eerie, deep, mysterious female narration for supernatural, paranormal, and dark cosmic stories.",
        best_for="Mystery, Paranormal, Dark Stories",
        rate="-7%",   # 0.93x speed
        pitch="-12Hz",
        audio_filter="equalizer=f=160:width_type=o:width=1.4:g=3.0,equalizer=f=3000:width_type=o:width=1.0:g=2.0",
    ),
    "hi_calm_female": VoiceProfile(
        id="hi_calm_female",
        edge_voice_id="hi-IN-SwaraNeural",
        name="🎙️ Calm Female Hindi (Science, Space & Storytelling)",
        gender="Female",
        language="Hindi",
        description="Gentle, cosmic wonder, clear and comforting tone for planetary journeys and space storytelling.",
        best_for="Science, Space & Storytelling",
        rate="-5%",   # 0.95x speed
        pitch="-2Hz",
        audio_filter="equalizer=f=220:width_type=o:width=1.0:g=1.5,equalizer=f=3800:width_type=o:width=1.0:g=1.8",
    ),
    "hi_cinematic_female": VoiceProfile(
        id="hi_cinematic_female",
        edge_voice_id="hi-IN-SwaraNeural",
        name="🎙️ Cinematic Female Hindi (Emotional & Mysterious Stories)",
        gender="Female",
        language="Hindi",
        description="Expressive, dramatic cinematic depth with subtle emotional presence.",
        best_for="Emotional & Mysterious Stories",
        rate="-8%",   # 0.92x speed
        pitch="-6Hz",
        audio_filter="equalizer=f=150:width_type=o:width=1.2:g=2.5,aecho=0.85:0.5:100:0.18",
    ),

    # =========================================================================
    # 🇺🇸🇬🇧 ENGLISH VOICES — SPACE / MYSTERY / SCIENCE
    # =========================================================================
    "en_deep_cinematic_male": VoiceProfile(
        id="en_deep_cinematic_male",
        edge_voice_id="en-US-ChristopherNeural",
        name="🎙️ Deep Cinematic American Male (Space Shorts, Universe, Black Holes) ⭐ BEST",
        gender="Male",
        language="English",
        description="Hollywood blockbuster documentary narrator. Deep bass, authoritative gravity, massive cosmic scale.",
        best_for="Space Shorts, Universe, Black Holes",
        rate="-8%",   # 0.92x speed
        pitch="-12Hz",
        audio_filter="equalizer=f=110:width_type=o:width=1.5:g=4.5,equalizer=f=3400:width_type=o:width=1.2:g=2.5,acompressor=threshold=-18dB:ratio=2.5:attack=10:release=120",
    ),
    "en_deep_british_male": VoiceProfile(
        id="en_deep_british_male",
        edge_voice_id="en-GB-RyanNeural",
        name="🎙️ Deep British Male (Premium Space Documentary)",
        gender="Male",
        language="English",
        description="BBC / Discovery Channel premium prestige documentary narrator. Refined, aristocratic, awe-inspiring.",
        best_for="Premium Space Documentary",
        rate="-8%",   # 0.92x speed
        pitch="-8Hz",
        audio_filter="equalizer=f=130:width_type=o:width=1.4:g=3.5,equalizer=f=3800:width_type=o:width=1.0:g=2.0",
    ),
    "en_calm_british_male": VoiceProfile(
        id="en_calm_british_male",
        edge_voice_id="en-GB-ThomasNeural",
        name="🎙️ Calm British Male (Science, Astronomy, Universe)",
        gender="Male",
        language="English",
        description="Thoughtful, scholarly, professorial narrator explaining astrophysics and deep spacetime concepts.",
        best_for="Science, Astronomy, Universe",
        rate="-6%",   # 0.94x speed
        pitch="-4Hz",
        audio_filter="equalizer=f=200:width_type=o:width=1.2:g=2.0,equalizer=f=3600:width_type=o:width=1.0:g=1.5",
    ),
    "en_cinematic_narrator": VoiceProfile(
        id="en_cinematic_narrator",
        edge_voice_id="en-US-GuyNeural",
        name="🎙️ Cinematic Male Narrator (Mystery, Aliens, Time Travel)",
        gender="Male",
        language="English",
        description="Suspenseful movie trailer narrator. Dramatic pacing, intense curiosity, alien mystery vibes.",
        best_for="Mystery, Aliens, Time Travel",
        rate="-8%",   # 0.92x speed
        pitch="-8Hz",
        audio_filter="equalizer=f=120:width_type=o:width=1.4:g=3.5,aecho=0.8:0.4:90:0.16",
    ),
    "en_deep_warm_male": VoiceProfile(
        id="en_deep_warm_male",
        edge_voice_id="en-US-EricNeural",
        name="🎙️ Deep Warm Male (Black Holes, Cosmic Events, Deep Space)",
        gender="Male",
        language="English",
        description="Rich, warm, comforting deep resonance. Makes viewers feel the breathtaking vastness of the universe.",
        best_for="Black Holes, Cosmic Events, Deep Space",
        rate="-8%",   # 0.92x speed
        pitch="-10Hz",
        audio_filter="equalizer=f=100:width_type=o:width=1.5:g=4.5,equalizer=f=3000:width_type=o:width=1.2:g=2.0",
    ),
    "en_authoritative_male": VoiceProfile(
        id="en_authoritative_male",
        edge_voice_id="en-US-RogerNeural",
        name="🎙️ Authoritative Male (Scientific Facts & Educational Content)",
        gender="Male",
        language="English",
        description="Commanding, scientific authority, trustworthy and factual delivery.",
        best_for="Scientific Facts & Educational Content",
        rate="-7%",   # 0.93x speed
        pitch="-6Hz",
        audio_filter="equalizer=f=140:width_type=o:width=1.4:g=3.0,equalizer=f=4000:width_type=o:width=1.0:g=2.2",
    ),
    "en_calm_female": VoiceProfile(
        id="en_calm_female",
        edge_voice_id="en-US-JennyNeural",
        name="🎙️ Calm Female (Space & Science Storytelling)",
        gender="Female",
        language="English",
        description="Clear, calm, elegant storytelling for space probes, exoplanets, and telescope discoveries.",
        best_for="Space & Science Storytelling",
        rate="-5%",   # 0.95x speed
        pitch="-2Hz",
        audio_filter="equalizer=f=220:width_type=o:width=1.0:g=1.5,equalizer=f=3600:width_type=o:width=1.0:g=1.8",
    ),
    "en_cinematic_female": VoiceProfile(
        id="en_cinematic_female",
        edge_voice_id="en-US-AriaNeural",
        name="🎙️ Cinematic Female (Mystery & Emotional Stories)",
        gender="Female",
        language="English",
        description="Expressive, dramatic cinematic female voice for unsolved mysteries, lost civilizations, and emotion.",
        best_for="Mystery & Emotional Stories",
        rate="-7%",   # 0.93x speed
        pitch="-6Hz",
        audio_filter="equalizer=f=160:width_type=o:width=1.2:g=2.5,aecho=0.85:0.5:100:0.18",
    ),

    # =========================================================================
    # BACKWARD COMPATIBILITY ALIASES
    # =========================================================================
    "akashvani": VoiceProfile(
        id="akashvani",
        edge_voice_id="hi-IN-MadhurNeural",
        name="🎙️ आकाशवाणी (Cosmic Echo Devavani - Divine Echo)",
        gender="Divine",
        language="Hindi",
        description="Gambhira Devavani / Cosmic Voice with divine echo & deep bass",
        best_for="Space, Cosmic Mysteries, Ancient Bharat",
        rate="-7%",
        pitch="-14Hz",
        audio_filter="aecho=0.85:0.75:100|220:0.35|0.2,equalizer=f=120:width_type=o:width=1.5:g=4,equalizer=f=3500:width_type=o:width=1.2:g=2",
    ),
    "madhur": VoiceProfile(
        id="madhur",
        edge_voice_id="hi-IN-MadhurNeural",
        name="Madhur",
        gender="Male",
        language="Hindi",
        description="Classic natural Hindi documentary narrator",
        best_for="Hindi documentaries and facts",
        rate="-6%",
        pitch="-8Hz",
        audio_filter="equalizer=f=120:width_type=o:width=1.5:g=3.5,equalizer=f=3200:width_type=o:width=1.2:g=2.0",
    ),
    "swara": VoiceProfile(
        id="swara",
        edge_voice_id="hi-IN-SwaraNeural",
        name="Swara",
        gender="Female",
        language="Hindi",
        description="Crisp expressive Indian female voice",
        best_for="Stories and mysteries",
        rate="-6%",
        pitch="-4Hz",
    ),
    "adam": VoiceProfile(
        id="adam",
        edge_voice_id="en-US-ChristopherNeural",
        name="Adam",
        gender="Male",
        language="English",
        description="Viral US male narrator",
        best_for="Viral Shorts",
        rate="-8%",
        pitch="-8Hz",
        audio_filter="equalizer=f=110:width_type=o:width=1.5:g=3.5,equalizer=f=3400:width_type=o:width=1.2:g=2.0",
    ),
    "christopher": VoiceProfile(
        id="christopher",
        edge_voice_id="en-US-ChristopherNeural",
        name="Christopher",
        gender="Male",
        language="English",
        description="Deep authoritative documentary style",
        best_for="Documentaries",
        rate="-8%",
        pitch="-10Hz",
        audio_filter="equalizer=f=110:width_type=o:width=1.5:g=4.0,equalizer=f=3400:width_type=o:width=1.2:g=2.5",
    ),
    "guy": VoiceProfile(
        id="guy",
        edge_voice_id="en-US-GuyNeural",
        name="Guy",
        gender="Male",
        language="English",
        description="Conversational storyteller",
        best_for="Shorts",
        rate="-4%",
        pitch="+0Hz",
    ),
    "aria": VoiceProfile(
        id="aria",
        edge_voice_id="en-US-AriaNeural",
        name="Aria",
        gender="Female",
        language="English",
        description="Expressive warm female",
        best_for="Documentaries",
        rate="-6%",
        pitch="-4Hz",
    ),
    "andrew": VoiceProfile(
        id="andrew",
        edge_voice_id="en-US-AndrewNeural",
        name="Andrew",
        gender="Male",
        language="English",
        description="Young dynamic tech voice",
        best_for="Tech and facts",
        rate="-4%",
        pitch="+0Hz",
    ),
    "ryan": VoiceProfile(
        id="ryan",
        edge_voice_id="en-GB-RyanNeural",
        name="Ryan",
        gender="Male",
        language="English",
        description="Refined British male narrator",
        best_for="Documentaries",
        rate="-8%",
        pitch="-8Hz",
    ),
}

# Alias lookups for common abbreviations
VOICE_ALIASES: Dict[str, str] = {
    "deep_cinematic_hi": "hi_deep_cinematic_male",
    "deep_hindi": "hi_deep_cinematic_male",
    "calm_hindi": "hi_calm_male",
    "cinematic_hindi": "hi_cinematic_male",
    "authoritative_hindi": "hi_authoritative_male",
    "young_hindi": "hi_young_male",
    "deep_female_hi": "hi_deep_female",
    "calm_female_hi": "hi_calm_female",
    "cinematic_female_hi": "hi_cinematic_female",
    "deep_cinematic_en": "en_deep_cinematic_male",
    "deep_american": "en_deep_cinematic_male",
    "deep_british": "en_deep_british_male",
    "calm_british": "en_calm_british_male",
    "cinematic_en": "en_cinematic_narrator",
    "deep_warm_en": "en_deep_warm_male",
    "authoritative_en": "en_authoritative_male",
    "calm_female_en": "en_calm_female",
    "cinematic_female_en": "en_cinematic_female",
}


def get_voice_profile(name_or_id: str) -> Optional[VoiceProfile]:
    """Return the VoiceProfile object for a key, alias, or direct Edge-TTS voice identifier."""
    if not name_or_id:
        return None
    key = name_or_id.lower().strip()
    # Check aliases first
    if key in VOICE_ALIASES:
        key = VOICE_ALIASES[key]
    if key in VOICE_CATALOG:
        return VOICE_CATALOG[key]
    # Check if value matches an edge_voice_id directly
    for p in VOICE_CATALOG.values():
        if p.edge_voice_id.lower() == key:
            return p
    return None


def get_voice_id(name_or_id: str) -> str:
    """Resolve a friendly voice name or direct ID to the full Edge-TTS voice identifier."""
    profile = get_voice_profile(name_or_id)
    if profile:
        return profile.edge_voice_id
    return name_or_id


def list_available_voices() -> List[VoiceProfile]:
    return list(VOICE_CATALOG.values())
