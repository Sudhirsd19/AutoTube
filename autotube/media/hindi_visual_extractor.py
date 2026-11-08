"""Hindi to English semantic visual concept extractor.

Accurately translates and maps spoken Hindi / Hinglish narration into high-relevance
English visual search queries and scene contracts for Pexels, Mixkit, Coverr, Pixabay,
and AI video engines.
"""

import os
import re
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Dict, Any, List, Optional
from autotube.config import get_config


# Devanagari Unicode range
DEVANAGARI_PATTERN = re.compile(r"[\u0900-\u097F]")
_EXTRACTOR_EXECUTOR = ThreadPoolExecutor(max_workers=2)


def is_hindi_text(text: str) -> bool:
    """Check if the text contains Devanagari characters or common Hinglish terms."""
    if not text:
        return False
    if DEVANAGARI_PATTERN.search(text):
        return True
    lower = text.lower()
    hinglish_markers = {
        "kya", "kyun", "kaise", "hota", "hoti", "hote", "raha", "rahi", "rahe",
        "nahi", "karte", "karein", "pehle", "baad", "andar", "bahar", "shuru",
        "dost", "dosto", "aapko", "hamare", "iski", "iske", "uska", "uske",
        "saal", "waqt", "samay", "duniya", "dharti", "antariksh", "brahmand",
        "samundar", "pahad", "mandir", "itihaas", "rahasya", "vigyan", "vaigyanik"
    }
    words = set(re.findall(r"[a-zA-Z]+", lower))
    return len(words.intersection(hinglish_markers)) >= 2


# Rich semantic dictionary: Hindi concepts -> English visual concepts
HINDI_VISUAL_CONCEPTS: List[Dict[str, Any]] = [
    # 1. DEEP SEA, OCEANS, UNDERWATER & WATER BODIES
    {
        "triggers": [
            "जहरीली झील", "जहरीला पानी", "अंडरवाटर लेक", "नमकीन झील", "toxic lake", "brine pool",
            "hyper-saline", "underwater lake"
        ],
        "subject": "toxic underwater brine pool deep ocean floor",
        "search_queries": ["underwater lake", "deep sea ocean floor", "brine pool underwater", "ocean abyss dark"],
        "must_show": ["underwater lake", "deep ocean abyss", "eerie underwater mist"],
        "avoid": ["sunny beach", "swimming pool", "city", "office", "cartoon"],
    },
    {
        "triggers": [
            "समुद्र", "समंदर", "सागर", "महासागर", "गहरा समुद्र", "समुद्र की गहराई", "abyss", "trench",
            "मरियाना ट्रेंच", "mariana trench", "samundar", "sagar", "deep sea"
        ],
        "subject": "deep dark ocean abyss and trench",
        "search_queries": ["deep sea ocean", "dark ocean abyss", "underwater deep blue", "ocean trench dark"],
        "must_show": ["dark deep ocean", "underwater abyss", "deep water depth"],
        "avoid": ["sunny beach", "swimming pool", "resort", "hotel", "office"],
    },
    {
        "triggers": [
            "पनडुब्बी", "सबमरीन", "सोनार", "रडार", "अंडरवाटर लाइट", "submarine", "sonar", "submersible",
            "underwater expedition"
        ],
        "subject": "underwater exploration submarine with headlights in dark sea",
        "search_queries": ["underwater submarine", "deep sea submarine lights", "ocean expedition submersible", "sonar screen radar"],
        "must_show": ["submarine in ocean", "underwater headlights", "deep sea exploration"],
        "avoid": ["beach", "swimming pool", "cartoon", "office"],
    },
    {
        "triggers": ["नदी", "झरना", "तालाब", "झील", "पानी", "जल", "नहर", "waterfall", "river", "lake"],
        "subject": "majestic wild river waterfall nature landscape",
        "search_queries": ["wild river flowing", "majestic waterfall nature", "mountain lake river", "clear water nature"],
        "must_show": ["flowing river", "waterfall nature", "clean natural water"],
        "avoid": ["office", "living room", "factory", "cartoon"],
    },

    # 2. SPACE, ASTRONOMY, BLACK HOLES & CELESTIAL
    {
        "triggers": [
            "ब्लैक होल", "कृष्ण विवर", "इवेंट होराइजन", "सिंगुलैरिटी", "black hole", "blackhole",
            "event horizon", "singularity", "spaghettification"
        ],
        "subject": "black hole cosmic event horizon and accretion disk",
        "search_queries": ["black hole space", "black hole vortex", "cosmic black hole", "deep space galaxy vortex"],
        "must_show": ["black hole", "cosmic vortex", "deep space", "singularity"],
        "avoid": ["earth daytime", "blue sky", "nature", "sunny", "phone", "office", "face mask"],
    },
    {
        "triggers": [
            "बृहस्पति", "जुपिटर", "jupiter", "gas giant", "great red spot", "विशालकाय गैसीय ग्रह"
        ],
        "subject": "planet Jupiter gas giant and turbulent storm clouds",
        "search_queries": ["jupiter planet space", "jupiter storm atmosphere", "gas giant planet", "jupiter great red spot"],
        "must_show": ["planet Jupiter", "cosmic gas giant", "planetary storm"],
        "avoid": ["earth daytime", "green grass", "people", "office", "sunny beach"],
    },
    {
        "triggers": ["शनि", "शनि ग्रह", "saturn", "planetary rings", "वलय"],
        "subject": "planet Saturn with golden rings orbiting in space",
        "search_queries": ["saturn planet rings", "saturn in space", "saturn golden rings", "planet cosmos"],
        "must_show": ["Saturn planet", "planetary rings", "deep space"],
        "avoid": ["earth daytime", "city", "people", "office"],
    },
    {
        "triggers": ["मंगल", "मंगल ग्रह", "लाल ग्रह", "mars", "red planet"],
        "subject": "planet Mars red surface with craters and canyons",
        "search_queries": ["mars planet red surface", "planet mars space", "martian landscape surface", "mars planet orbit"],
        "must_show": ["Mars planet", "red planetary landscape", "craters"],
        "avoid": ["green trees", "ocean", "city", "people"],
    },
    {
        "triggers": ["सूर्य", "सूरज", "सौर ज्वाला", "सन", "sun", "solar flare", "solar corona"],
        "subject": "sun surface with fiery solar flares and corona",
        "search_queries": ["sun solar flare space", "sun surface glowing", "solar corona space", "glowing sun star"],
        "must_show": ["Sun surface", "solar flares", "glowing corona"],
        "avoid": ["earth daytime", "people", "city", "clouds"],
    },
    {
        "triggers": ["चांद", "चंद्रमा", "लूनर", "moon", "lunar surface"],
        "subject": "moon surface with craters orbiting Earth in dark space",
        "search_queries": ["moon surface craters", "moon in deep space", "lunar surface orbit", "moon earth space"],
        "must_show": ["Moon surface", "craters", "deep space"],
        "avoid": ["daytime sky", "people", "trees"],
    },
    {
        "triggers": [
            "उल्कापिंड", "धूमकेतु", "क्षुद्रग्रह", "एस्ट्रोइड", "मिटियोर", "meteor", "asteroid", "comet",
            "meteorite", "cosmic collision"
        ],
        "subject": "giant fiery asteroid hurtling through space towards planet",
        "search_queries": ["asteroid flying space", "fiery meteor deep space", "comet asteroid cosmos", "meteor impact earth"],
        "must_show": ["asteroid in space", "fiery tail", "cosmic rock"],
        "avoid": ["office", "people", "car", "room"],
    },
    {
        "triggers": [
            "अंतरिक्ष", "ब्रह्मांड", "आकाशगंगा", "तारे", "नेबुला", "मिल्की वे", "कौस्मॉस",
            "space", "antariksh", "brahmand", "galaxy", "universe", "stars", "nebula", "milky way", "cosmos"
        ],
        "subject": "deep outer space with colorful nebula and rotating spiral galaxy",
        "search_queries": ["deep space galaxy", "milky way stars universe", "colorful nebula space", "outer space cosmos"],
        "must_show": ["deep space", "stars galaxy", "cosmic nebula"],
        "avoid": ["earth daytime", "city", "people", "office", "beach"],
    },
    {
        "triggers": [
            "पृथ्वी", "धरती", "नीला ग्रह", "earth", "planet earth", "dharati", "globe"
        ],
        "subject": "planet Earth viewed from space rotating with blue atmosphere",
        "search_queries": ["planet earth from space", "earth rotating space", "blue planet earth", "earth atmosphere space"],
        "must_show": ["Earth from space", "blue oceans continents", "atmosphere rim"],
        "avoid": ["flat earth cartoon", "indoor", "room"],
    },

    # 3. ANCIENT HISTORY, TEMPLES, SACRED & ARCHAEOLOGY
    {
        "triggers": [
            "कैलाश मंदिर", "कैलासा", "एलोरा", "एक ही पत्थर", "चट्टान काटकर", "kailasa temple", "ellora",
            "monolithic rock temple"
        ],
        "subject": "ancient Kailasa monolithic rock temple carved from top to bottom",
        "search_queries": ["ancient stone temple ruins", "kailasa temple ellora", "ancient rock carved temple", "ancient indian architecture"],
        "must_show": ["ancient rock temple", "intricate stone pillars", "monolithic carving"],
        "avoid": ["modern office", "cars", "outer space", "smartphone", "neon"],
    },
    {
        "triggers": [
            "द्वारका", "डूबी हुई नगरी", "पानी में डूबा शहर", "dwarka", "submerged city", "sunken ruins"
        ],
        "subject": "underwater ancient submerged stone city ruins",
        "search_queries": ["underwater ancient ruins", "submerged stone city", "underwater temple ruins", "ancient sunken city"],
        "must_show": ["underwater stone ruins", "ancient pillars submerged", "ancient sunken stone"],
        "avoid": ["modern submarine cartoon", "office", "cars"],
    },
    {
        "triggers": [
            "मंदिर", "प्राचीन मंदिर", "मंदिर का रहस्य", "शिलालेख", "नक्काशी", "वास्तु",
            "temple", "mandir", "ancient temple", "stone carvings", "shilalekh"
        ],
        "subject": "ancient Indian stone temple with intricate carvings at golden hour",
        "search_queries": ["ancient indian temple", "stone temple carvings", "ancient temple architecture", "ancient stone ruins"],
        "must_show": ["ancient stone temple", "intricate carvings", "majestic architecture"],
        "avoid": ["modern city", "cars", "office", "outer space", "smartphone"],
    },
    {
        "triggers": [
            "महाभारत", "कुरुक्षेत्र", "युद्ध", "सेना", "सैनिक", "धनुष बाण", "तीर", "तलवार",
            "mahabharat", "kurukshetra", "battlefield", "ancient war", "warriors"
        ],
        "subject": "ancient epic battlefield with warriors shields and dramatic smoke",
        "search_queries": ["ancient battlefield warriors", "ancient war army dramatic", "epic historical battle soldiers", "ancient warriors dramatic"],
        "must_show": ["ancient warriors", "battlefield smoke", "shields and weapons"],
        "avoid": ["modern tanks", "rifles", "city cars", "office", "smartphone"],
    },
    {
        "triggers": [
            "खुदाई", "अवशेष", "पुरातत्व", "वैज्ञानिक खुदाई", "हड़प्पा", "सिंधु घाटी", "पिरामिड",
            "archaeological excavation", "excavation", "ancient artifacts", "ruins", "fossils"
        ],
        "subject": "archaeological excavation site with ancient stone artifacts",
        "search_queries": ["archaeological excavation site", "ancient artifacts discovery", "ancient stone ruins dramatic", "archaeologists examining artifacts"],
        "must_show": ["excavation site", "ancient stone relics", "archaeological discovery"],
        "avoid": ["modern skyscrapers", "office", "living room"],
    },
    {
        "triggers": [
            "ग्रंथ", "प्राचीन पांडुलिपि", "शास्त्र", "वेद", "उपनिषद", "श्लोक", "ताड़पत्र",
            "ancient manuscript", "sacred scripture", "scroll", "vedic text"
        ],
        "subject": "ancient sacred manuscript scroll with authentic calligraphy by oil lamp",
        "search_queries": ["ancient manuscript scroll", "ancient sacred scripture", "old parchment manuscript", "historical ancient documents"],
        "must_show": ["ancient manuscript", "parchment paper", "oil lamp lighting"],
        "avoid": ["modern book print", "laptop", "smartphone", "office"],
    },
    {
        "triggers": ["राजा", "सम्राट", "सिंहासन", "महल", "शाही दरबार", "king", "palace", "emperor", "throne"],
        "subject": "ancient royal palace courtroom with majestic golden throne",
        "search_queries": ["ancient royal palace", "majestic stone palace", "historical ancient throne", "ancient palace architecture"],
        "must_show": ["ancient palace", "majestic architecture", "pillars royal"],
        "avoid": ["modern office", "cars", "smartphone"],
    },

    # 4. SCIENCE, TECHNOLOGY, ROBOTS & AI
    {
        "triggers": [
            "रोबोट", "ह्यूमनॉइड रोबोट", "आर्टिफिशियल इंटेलिजेंस", "एआई", "मशीन", "robot", "humanoid robot",
            "artificial intelligence", "ai robot", "cyborg"
        ],
        "subject": "futuristic advanced humanoid robot with glowing blue neural eyes",
        "search_queries": ["humanoid robot futuristic", "artificial intelligence robot", "futuristic technology robot", "advanced robotics laboratory"],
        "must_show": ["humanoid robot", "futuristic technology", "robotic face"],
        "avoid": ["cartoon", "toy", "vintage retro 1950s robot"],
    },
    {
        "triggers": [
            "वैज्ञानिक", "प्रयोगशाला", "रिसर्च", "माइक्रोस्कोप", "शोध", "जांच", "लैब",
            "scientist", "laboratory", "microscope", "science experiment", "researchers"
        ],
        "subject": "scientists conducting advanced research in modern high-tech laboratory",
        "search_queries": ["scientists in laboratory", "science research microscope", "high tech laboratory", "scientific experiment glass"],
        "must_show": ["scientists in lab coats", "laboratory equipment", "microscope or test tubes"],
        "avoid": ["messy kitchen", "cartoon", "garage"],
    },
    {
        "triggers": [
            "डीएनए", "जीन", "वायरस", "कोशिका", "सेल", "आनुवंशिकी", "dna", "genetics", "virus", "cells", "molecules"
        ],
        "subject": "glowing 3D DNA double helix rotating with microscopic cells",
        "search_queries": ["dna double helix 3d", "microscopic cells biology", "molecular genetics science", "glowing dna medical"],
        "must_show": ["rotating DNA strand", "microscopic biology", "glowing molecules"],
        "avoid": ["cartoon", "hospital bed", "pills"],
    },
    {
        "triggers": [
            "कंप्यूटर", "हैकर", "डेटा", "साइबर", "कोडिंग", "सर्वर", "computer code", "hacker", "cyber data", "server room"
        ],
        "subject": "glowing digital data streams in futuristic server room",
        "search_queries": ["futuristic server room data", "cyber digital code glowing", "high tech computer data", "binary digital streams"],
        "must_show": ["glowing server racks", "digital data stream", "cyber technology"],
        "avoid": ["broken laptop", "messy bedroom", "cartoon"],
    },

    # 5. NATURE, ANIMALS, WILDLIFE & DISASTERS
    {
        "triggers": ["शेर", "बब्बर शेर", "शेर का शिकार", "lion", "african lion", "king of jungle"],
        "subject": "majestic wild male lion walking in savanna grassland",
        "search_queries": ["wild male lion", "lion walking savanna", "lion closeup majestic", "african lion wildlife"],
        "must_show": ["male lion with mane", "wild savanna", "predator wildlife"],
        "avoid": ["zoo cage", "cartoon", "stuffed toy", "circus"],
    },
    {
        "triggers": ["बाघ", "चीता", "तेंदुआ", "tiger", "bengal tiger", "leopard", "cheetah"],
        "subject": "fierce royal Bengal tiger walking through lush green jungle",
        "search_queries": ["bengal tiger jungle", "wild tiger walking", "leopard predator wildlife", "tiger closeup majestic"],
        "must_show": ["Bengal tiger", "wild green jungle", "predator gaze"],
        "avoid": ["zoo cage", "cartoon", "circus"],
    },
    {
        "triggers": ["चील", "बाज", "उड़ान", "शिकारी पक्षी", "eagle", "hawk", "falcon", "flying eagle"],
        "subject": "majestic golden eagle soaring through mountain clouds",
        "search_queries": ["golden eagle flying", "eagle soaring mountains", "predator eagle flying sky", "eagle closeup eyes"],
        "must_show": ["flying eagle", "wide wingspan", "sky mountains"],
        "avoid": ["cage", "cartoon", "poultry farm"],
    },
    {
        "triggers": ["शार्क", "व्हेल", "व्हेल मछली", "shark", "great white shark", "whale", "blue whale"],
        "subject": "massive great white shark swimming in deep ocean blue water",
        "search_queries": ["great white shark underwater", "whale swimming deep ocean", "shark underwater ocean", "massive whale deep sea"],
        "must_show": ["shark underwater", "deep blue sea", "marine wildlife"],
        "avoid": ["aquarium tank", "cartoon", "fishing boat"],
    },
    {
        "triggers": ["सांप", "अजगर", "किंग कोबरा", "snake", "king cobra", "python"],
        "subject": "hooded King Cobra in dark rainforest jungle",
        "search_queries": ["king cobra snake", "snake crawling jungle", "reptile predator snake", "viper snake wild"],
        "must_show": ["King Cobra", "scales and eyes", "wild rainforest"],
        "avoid": ["pet cage", "cartoon", "toy"],
    },
    {
        "triggers": ["हाथी", "गजराज", "elephant", "wild elephant", "herd of elephants"],
        "subject": "majestic wild elephant walking through dense forest mist",
        "search_queries": ["wild elephant walking", "asian elephant jungle", "elephant herd nature", "majestic elephant wild"],
        "must_show": ["wild elephant", "tusks and trunk", "natural forest"],
        "avoid": ["circus", "cartoon", "temple chains"],
    },
    {
        "triggers": ["ज्वालामुखी", "लावा", "धमाका", "विस्फोट", "volcano", "lava", "volcanic eruption", "explosion"],
        "subject": "active volcano erupting glowing red lava and dark smoke clouds",
        "search_queries": ["volcano erupting lava", "flowing red lava volcano", "volcanic explosion smoke", "dramatic volcano night"],
        "must_show": ["erupting volcano", "glowing red lava", "volcanic smoke"],
        "avoid": ["office", "people smiling", "cartoon"],
    },
    {
        "triggers": ["तूफान", "चक्रवात", "बवंडर", "बिजली", "बिजली गिरना", "storm", "hurricane", "tornado", "lightning"],
        "subject": "massive thunderstorm with dramatic lightning striking dark clouds",
        "search_queries": ["lightning striking storm", "thunderstorm dark clouds", "tornado supercell storm", "hurricane ocean storm"],
        "must_show": ["lightning bolt", "dark thunder clouds", "storm power"],
        "avoid": ["sunny day", "blue sky", "cartoon"],
    },
    {
        "triggers": ["जंगल", "घना जंगल", "अमेजन", "रेनफॉरेस्ट", "jungle", "forest", "rainforest", "deep woods"],
        "subject": "lush green deep rainforest canopy with morning sunbeams through mist",
        "search_queries": ["deep rainforest jungle", "misty forest sunbeams", "tropical rainforest trees", "wild green jungle aerial"],
        "must_show": ["deep forest canopy", "lush green trees", "misty atmosphere"],
        "avoid": ["city park", "cleared land", "office"],
    },
    {
        "triggers": ["रेगिस्तान", "थार", "रेत के टीले", "सहारा", "desert", "sand dunes", "sahara"],
        "subject": "endless golden sand dunes in desert at sunset",
        "search_queries": ["desert sand dunes sunset", "golden sahara desert", "wind blowing desert sand", "desert landscape aerial"],
        "must_show": ["golden sand dunes", "wind patterns", "vast desert"],
        "avoid": ["ocean", "green forest", "city"],
    },
    {
        "triggers": ["बर्फ", "ग्लेशियर", "अंटार्कटिका", "बर्फबारी", "snow", "glacier", "antarctica", "iceberg"],
        "subject": "majestic frozen blue glacier and icebergs in Antarctica",
        "search_queries": ["glacier icebergs ocean", "antarctica ice mountains", "frozen glacier blue ice", "snow mountain peak"],
        "must_show": ["blue ice glacier", "iceberg ocean", "frozen landscape"],
        "avoid": ["green summer trees", "sunny beach", "city"],
    },

    # 6. MYSTERY, SUPERNATURAL, ALIEN & MILITARY
    {
        "triggers": ["एलियन", "यूएफओ", "रोसवेल", "दूसरे ग्रह का जीव", "alien", "ufo", "roswell", "extraterrestrial"],
        "subject": "mysterious flying saucer UFO hovering over desert at dusk",
        "search_queries": ["flying saucer ufo sky", "alien mystery desert", "mysterious glowing ufo", "sci fi alien phenomenon"],
        "must_show": ["UFO craft", "eerie lights", "desert mystery"],
        "avoid": ["cartoon", "toy", "office"],
    },
    {
        "triggers": ["भूत", "साया", "डरावना", "भूतिया", "रहस्यमयी साया", "haunted", "ghost", "shadow figure", "eerie"],
        "subject": "dark shadowy mysterious silhouette in misty abandoned hallway",
        "search_queries": ["dark shadowy silhouette", "mysterious misty corridor", "eerie dark atmosphere", "abandoned dark hallway"],
        "must_show": ["shadowy figure", "dark mist", "eerie atmospheric lighting"],
        "avoid": ["sunny day", "party", "smiling people", "cartoon"],
    },
    {
        "triggers": ["सेना", "फौज", "कमांडो", "टैंक", "लड़ाकू विमान", "हथियार", "army", "military", "tank", "fighter jet"],
        "subject": "military tactical special forces commando team moving in stealth",
        "search_queries": ["military tactical forces", "fighter jet flying sky", "military tank battlefield", "stealth special forces"],
        "must_show": ["military tactical gear", "dramatic lighting", "defense force"],
        "avoid": ["children playground", "office", "cartoon"],
    },
    {
        "triggers": [
            "सीआईए", "एफबीआई", "गुप्त दस्तावेज", "डीक्लासिफाइड फाइल", "खूफिया",
            "cia document", "classified files", "declassified", "top secret"
        ],
        "subject": "vintage top secret declassified government documents with stamps",
        "search_queries": ["top secret documents file", "vintage detective investigation", "declassified government files", "classified confidential papers"],
        "must_show": ["secret file stamped", "aged paper documents", "vintage office desk"],
        "avoid": ["modern smartphone", "cartoon", "bright daylight beach"],
    },
    {
        "triggers": ["खजाना", "सोना", "सोने के सिक्के", "तिजोरी", "धन", "treasure", "gold coins", "bank vault"],
        "subject": "ancient chest overflowing with sparkling gold coins and gems",
        "search_queries": ["gold coins treasure glowing", "ancient treasure chest gold", "massive bank vault opening", "sparkling gold bullion"],
        "must_show": ["gold coins treasure", "sparkling golden light", "ancient wealth"],
        "avoid": ["empty room", "plastic toys", "cartoon"],
    },

    # 7. HUMAN PSYCHOLOGY, BRAIN & MIND
    {
        "triggers": [
            "दिमाग", "मस्तिष्क", "न्यूरॉन", "सोच", "याददाश्त", "सबकॉन्शियस",
            "brain", "mind", "neurons", "subconscious", "psychology", "memory"
        ],
        "subject": "human brain with glowing neural networks and synapses firing electrical pulses",
        "search_queries": ["glowing brain neural network", "human brain neurons firing", "abstract subconscious mind", "neural synapses glowing"],
        "must_show": ["glowing brain", "firing neural synapses", "abstract thought network"],
        "avoid": ["hospital surgery", "doctor with scalpel", "cartoon", "zombie"],
    },
    {
        "triggers": ["आंख", "पुतली", "आंखों में डर", "eye", "human eye pupil", "iris closeup"],
        "subject": "extreme macro cinematic closeup of human eye pupil dilating",
        "search_queries": ["human eye pupil macro", "eye iris closeup cinematic", "dilating pupil closeup", "human eye reflection"],
        "must_show": ["macro eye closeup", "iris details", "dramatic pupil"],
        "avoid": ["glasses reflection", "cartoon", "makeup tutorial"],
    },
]


def extract_english_visual_queries(
    narration: str,
    topic: str = "",
    scene_idx: int = 0,
) -> Dict[str, Any]:
    """Analyze spoken narration (Hindi, Hinglish, or English) and extract clean,

    actionable English visual subjects and queries suitable for stock video engines.
    """
    raw_text = (narration or "").strip()
    clean_topic = (topic or "").strip()
    combined_lower = f"{clean_topic.lower()} {raw_text.lower()}"

    # -------------------------------------------------------------
    # STEP 1: Gemini AI Semantic Extraction (Primary & Contextual Extraction)
    # -------------------------------------------------------------
    cfg = get_config()
    gemini_key = os.getenv("GEMINI_API_KEY", "") or getattr(cfg, "gemini_api_key", "")
    if gemini_key:
        def _call_ai():
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            prompt = f"""You are an elite video director sourcing exact visual footage for a viral video.
Topic/Title: "{clean_topic}"
Current Scene #{scene_idx + 1} Spoken Narration: "{raw_text}"

TASK:
1. Understand the exact physical subject and action described in this sentence.
2. Provide 3-4 clean, precise (2-4 words each) English search keywords that stock video libraries (Pexels, Mixkit, Coverr, Pixabay) and YouTube Shorts ACTUALLY index footage under.
3. Identify the main physical visual subject.

STRICT ACCURACY RULES:
- If the narration mentions an animal, insect, or plant (e.g. jaguar, crocodile, exploding seed pod, eagle), search queries MUST feature that exact animal/plant.
- If it mentions a specific machine, experiment, or vehicle (e.g. submarine, rocket, particle collider), queries MUST feature that subject.
- If it mentions underwater / ocean floor / brine pool, queries MUST be about underwater deep sea.
- If it mentions space / black hole / event horizon / time dilation, queries MUST be space astrophysics.
- If it mentions ancient temples, architecture, or history, queries MUST be ancient temples / archaeology.
- NEVER invent unrelated outer space, generic waterfalls, or random rooms for specific real-world stories.

Return JSON only:
{{
  "subject": "concise 2-4 word English subject",
  "search_queries": ["exact query 1", "exact query 2", "exact query 3"],
  "must_show": ["concrete visual element 1", "element 2"],
  "avoid": ["unrelated element 1", "element 2"],
  "visual_description": "1 clear sentence describing what the viewer should see"
}}"""
            for m in ("gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.8-flash"):
                try:
                    resp = client.models.generate_content(
                        model=m,
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json"),
                    )
                    if resp and resp.text:
                        return resp.text
                except Exception:
                    continue
            return None

        try:
            future = _EXTRACTOR_EXECUTOR.submit(_call_ai)
            ai_text = future.result(timeout=7.5)
            if ai_text:
                clean_json = ai_text.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:].split("```")[0].strip()
                elif clean_json.startswith("```"):
                    clean_json = clean_json[3:].split("```")[0].strip()
                data = json.loads(clean_json)
                if data.get("subject") and data.get("search_queries"):
                    clean_qs = [
                        re.sub(r"[^a-zA-Z0-9\s-]", "", str(q)).strip()
                        for q in data.get("search_queries", [])
                        if str(q).strip()
                    ]
                    clean_qs = [q for q in clean_qs if len(q) > 1][:4]
                    if clean_qs:
                        return {
                            "subject": str(data.get("subject", "cinematic scene")).strip(),
                            "search_queries": clean_qs,
                            "must_show": [str(m).strip() for m in data.get("must_show", []) if str(m).strip()][:4],
                            "avoid": [str(a).strip() for a in data.get("avoid", []) if str(a).strip()][:6],
                            "visual_description": str(data.get("visual_description", "")).strip(),
                            "mode": "ai_extracted",
                        }
        except (TimeoutError, Exception):
            pass

    # -------------------------------------------------------------
    # STEP 2: Semantic dictionary fallback (Only when AI is unavailable, requiring meaningful phrases)
    # -------------------------------------------------------------
    for concept in HINDI_VISUAL_CONCEPTS:
        triggers = concept.get("triggers", [])
        meaningful_triggers = [t for t in triggers if len(t) >= 4 or " " in t]
        if any(trig in raw_text.lower() for trig in meaningful_triggers):
            return {
                "subject": concept["subject"],
                "search_queries": list(concept["search_queries"]),
                "must_show": list(concept["must_show"]),
                "avoid": list(concept["avoid"]),
                "visual_description": f"Cinematic visual depicting {concept['subject']}",
                "mode": "concept_matched_sentence",
            }

    # -------------------------------------------------------------
    # STEP 3: Topic / Combined concept matching
    # -------------------------------------------------------------
    for concept in HINDI_VISUAL_CONCEPTS:
        triggers = concept.get("triggers", [])
        if any(trig in combined_lower for trig in triggers):
            return {
                "subject": concept["subject"],
                "search_queries": list(concept["search_queries"]),
                "must_show": list(concept["must_show"]),
                "avoid": list(concept["avoid"]),
                "visual_description": f"Cinematic visual depicting {concept['subject']}",
                "mode": "concept_matched_topic",
            }

    # -------------------------------------------------------------
    # STEP 4: Fallback English Keywords Extraction from Mixed Text
    # -------------------------------------------------------------
    eng_words = [
        w for w in re.findall(r"[a-zA-Z]{3,}", raw_text)
        if w.lower() not in {
            "the", "and", "for", "with", "from", "that", "this", "what", "when",
            "karein", "rahe", "hote", "apna", "apne", "kuch", "baat", "nahi", "hota"
        }
    ]
    if len(eng_words) >= 2:
        subject = f"{' '.join(eng_words[:2])} cinematic"
        return {
            "subject": subject,
            "search_queries": [
                f"{' '.join(eng_words[:2])} cinematic",
                f"{eng_words[0]} dramatic",
                f"{eng_words[1]} detailed",
            ],
            "must_show": [eng_words[0], eng_words[1]],
            "avoid": ["modern office", "cartoon", "smartphone"],
            "visual_description": f"Cinematic shot of {subject}",
            "mode": "latin_tokens",
        }

    # General High-Quality Cinematic Fallback
    general_styles = [
        ("deep space galaxy cosmos", ["deep space galaxy", "cosmic stars galaxy", "outer space nebula"]),
        ("ancient stone temple ruins", ["ancient stone temple", "ancient temple ruins", "stone carvings ancient"]),
        ("dark deep ocean abyss", ["dark deep ocean", "underwater deep sea", "ocean abyss dark"]),
        ("mysterious dramatic atmosphere", ["cinematic dramatic mystery", "dark moody atmospheric", "atmospheric mystery suspense"]),
    ]
    chosen = general_styles[scene_idx % len(general_styles)]
    return {
        "subject": chosen[0],
        "search_queries": chosen[1],
        "must_show": [chosen[0].split()[0], chosen[0].split()[1]],
        "avoid": ["modern office", "cartoon", "smartphone", "daylight beach"],
        "visual_description": f"Atmospheric cinematic shot of {chosen[0]}",
        "mode": "genre_fallback",
    }
