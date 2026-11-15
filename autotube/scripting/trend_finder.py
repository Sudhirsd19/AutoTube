"""Trending Topic Finder & Anti-Repetition Deduplication Engine."""

import difflib
import json
import random
import re
import time
import unicodedata
from pathlib import Path
from typing import List, Optional, Set, Tuple

from autotube.config import PROJECT_ROOT, get_config
from autotube.scripting.generator import CANDIDATE_MODELS
from autotube.utils.console import print_info, print_success, print_warning
from google import genai
from google.genai import types

HISTORY_FILE = PROJECT_ROOT / "config" / "published_history.json"

# Niche keywords to canonical category mapping
NICHE_KEYWORD_MAPPINGS = {
    "mind glitch": "psychology",
    "subconscious": "psychology",
    "dark psychology": "psychology",
    "body language": "psychology",
    "psychology": "psychology",
    "quantum": "science",
    "science": "science",
    "physics": "science",
    "biology": "science",
    "bharat": "bharat_vigyan",
    "vigyan": "bharat_vigyan",
    "prachin": "bharat_vigyan",
    "प्राचीन": "bharat_vigyan",
    "मंदिर": "bharat_vigyan",
    "simulation": "glitch_matrix",
    "matrix": "glitch_matrix",
    "ocean": "ocean",
    "deep earth": "ocean",
    "sea": "ocean",
    "trench": "ocean",
    "itihas": "history",
    "history": "history",
    "khopiya": "history",
    "cosmic": "space",
    "space": "space",
    "universe": "space",
    "astronomy": "space",
    "ai & future": "ai_future",
    "ai": "ai_future",
    "artificial intelligence": "ai_future",
    "declassified": "conspiracy",
    "conspiracies": "conspiracy",
    "secret": "conspiracy",
    "mythology": "mythology",
    "cartoon": "cartoon",
    "animation": "cartoon",
    "mystery": "mystery",
    "animal": "animal_secrets",
    "creature": "animal_secrets",
    "bird": "animal_secrets",
    "wildlife": "animal_secrets",
    "beast": "animal_secrets",
    "जानवर": "animal_secrets",
    "जीव": "animal_secrets",
    "ancient engineering": "ancient_engineering",
    "ancient tech": "ancient_engineering",
    "megalith": "ancient_engineering",
    "pyramid": "ancient_engineering",
    "gobekli": "ancient_engineering",
    "kailasa": "ancient_engineering",
    "quantum matrix": "quantum_matrix",
    "quantum paradox": "quantum_matrix",
    "simulation bug": "quantum_matrix",
    "simulation glitch": "quantum_matrix",
    "time dilation": "quantum_matrix",
    "daily mirror": "daily_mirror",
    "daily_mirror": "daily_mirror",
    "daily theme": "daily_mirror",
    "daily_theme": "daily_mirror",
}

GITA_MOTIVATION_FALLBACK_FOCUS = (
    "Bhagavad Gita and ancient Indian scripture life lessons, karma yoga, self-discipline, "
    "resilience, non-attachment, inner peace, ethical choices and practical motivation. "
    "Never invent quotations, chapter numbers or scientific claims attributed to scripture."
)


VIRAL_NICHES = {
    "space": "Mind-bending cosmic mysteries, black holes, rogue planets, cosmic radiation, universe boundaries, quantum vacuum decay",
    "science": "Shocking physics paradoxes, quantum mechanics anomalies, strange biology glitches, crazy discoveries, time perception",
    "history": "Bizarre historical events, untold ancient secrets, ruthless rulers, hidden lost libraries, catastrophic ancient events",
    "psychology": "Dark psychology, human mind tricks, subconscious cognitive biases, body language micro-expressions, manipulation defense",
    "mystery": "Unsolved global enigmas, deep earth anomalies, forbidden archaeological discoveries, eerie legends, impossible ancient maps",
    "mythology": "Ancient Indian mythological secrets, sacred divine weapons, unsolved epic mysteries, lost temples, celestial beings",
    "gita_motivation": GITA_MOTIVATION_FALLBACK_FOCUS,
    "bharat_vigyan": "Bharat Ka Adbhut Vigyan: Kailasa Temple Ellora impossible monolithic carving from top down, Padmanabhaswamy Vault B acoustic snake lock, Delhi Iron Pillar 1600-year rustproof mystery, Ram Setu floating stone acoustics, Lepakshi hanging pillar gravity anomaly, Brihadeeswarar Temple 80-ton granite dome science",
    "glitch_matrix": "Glitch in the Matrix & Time Slips: The Man from Taured 1954 mystery, Pan American Flight 914 37-year time jump, Green Children of Woolpit, simulation hypothesis physical proofs, parallel universe sightings, quantum timeline shifts, deja vu glitches",
    "ocean": "Deep sea abyssal horrors, Mariana Trench sonar anomalies, Point Nemo alien sounds, giant colossal squids, glowing ocean milky seas, deep underwater brine pools",
    "ai_future": "Artificial general intelligence consciousness, dead internet theory, brain-computer neural lace risks, quantum cryptography collapse, synthetic biology paradoxes",
    "conspiracy": "Declassified FBI & CIA files, Project Stargate remote viewing, Guy Hottel UFO memos, Area 51 secret reverse engineering, Svalbard seed vault mysteries",
    "cartoon": "Funny 3D Pixar animated animal adventures, quirky pets with secret superhero lives, hilarious baby dinosaur mishaps, funny mischievous robot fails, adorable comedy cartoon stories",
    "animal_secrets": "Mind-blowing animal secrets, insane biological superpowers, animal speed & flight comparisons (Peregrine falcon 390 km/h dive vs cheetah, bite forces of apex predators), immortal jellyfish, pistol shrimp thermal shockwave, honey badger venom immunity, bizarre deep sea creatures, electric eel shock voltage",
    "ancient_engineering": "Impossible Ancient Engineering & Megaliths: Kailasa Temple Ellora monolithic rock carving from top down, Great Pyramids Giza acoustic & thermal anomalies, Göbekli Tepe 12,000-year megaliths, Antikythera Mechanism 2,000-year analog computer, Puma Punku precision stones, submerged Dwarka megaliths, Machu Picchu earthquake-proof masonry",
    "quantum_matrix": "Quantum Paradoxes & Simulation Reality: The Quantum Zeno effect freezing atoms under observation, Time dilation traps where your head ages faster than your feet, Boltzmann brain paradox, vacuum decay cosmic bubble, double slit experiment observer effect, simulation hypothesis physical proofs",
}

# 7-Day Content Schedule Tailored specifically for English (USA / Global Audience)
DAY_WISE_NICHES_EN = {
    0: {  # Monday
        "niche": "space",
        "name": "Cosmic Extremes & Deep Space Horrors",
        "bgm": "space",
        "description": "Mind-bending cosmic mysteries for US audience: Supermassive black hole event horizons, rogue planet collision orbits, quantum vacuum decay, Fermi paradox scary solutions, James Webb space telescope anomalies, strange signals from deep space",
    },
    1: {  # Tuesday
        "niche": "glitch_matrix",
        "name": "Simulation Glitches & Parallel Universes",
        "bgm": "space",
        "description": "Glitch in the matrix & simulation theory for US audience: The 1954 Man from Taured, Pan American Flight 914 37-year time jump, real physical evidence we live in a computed simulation, quantum timeline shifts, shared mass false memories (Mandela effect), time slip testimonies",
    },
    2: {  # Wednesday
        "niche": "psychology",
        "name": "Dark Psychology & FBI Profiling Secrets",
        "bgm": "auto",
        "description": "Dark psychology, behavioral profiling & FBI interrogation tactics for US audience: Subconscious cognitive bias exploitation, micro-expression deception spotting, emotional manipulation defense, linguistic markers of lying, Machiavellian psychological tricks",
    },
    3: {  # Thursday
        "niche": "ocean",
        "name": "Deep Ocean Horrors & Abyssal Anomalies",
        "bgm": "space",
        "description": "Deep sea abyssal terrors & oceanic anomalies for US audience: Mariana Trench extreme depth sound anomalies, Point Nemo oceanic pole of inaccessibility, giant colossal squids, deep toxic underwater brine lakes, underwater sonar anomalies like The Bloop and Julia",
    },
    4: {  # Friday
        "niche": "quantum_matrix",
        "name": "Quantum Paradoxes & Simulation Reality",
        "bgm": "space",
        "description": "Quantum paradoxes & simulation physics for US audience: The Quantum Zeno effect freezing reality under observation, Boltzmann brain paradox, vacuum decay cosmic bubble, quantum entanglement spooky action, time dilation traps, AI emergent consciousness",
    },
    5: {  # Saturday - Tailored for USA Audience (Declassified Secrets & Government Conspiracies)
        "niche": "conspiracy",
        "name": "Declassified FBI & CIA Secrets / US Government Conspiracies",
        "bgm": "history",
        "description": "Declassified US government, FBI & CIA secret files: Project Stargate remote viewing psychic experiments, Area 51 secret reverse-engineering files, Operation Starfish Prime nuclear space detonation, Project MKUltra cognitive experiments, Svalbard global seed vault, 1947 Roswell declassified memos, hidden DARPA projects",
    },
    6: {  # Sunday - High Engagement American Mysteries
        "niche": "mystery",
        "name": "Unsolved American Enigmas & Bizarre Disappearances",
        "bgm": "history",
        "description": "Unsolved enigmas and eerie anomalies for US audience: Skinwalker Ranch electromagnetic and animal mutilation anomalies, the vanished Roanoke colony, bizarre national park vanishings (Missing 411 phenomena), Dyatlov Pass anomaly, Voynich manuscript cryptanalysis failure",
    },
}

# 7-Day Content Schedule Tailored specifically for Hindi Audience (@bgyanmantra)
DAY_WISE_NICHES_HI = {
    0: {  # Monday
        "niche": "space",
        "name": "अंतरिक्ष व ब्रह्मांड के रहस्य (Cosmic Space & Universe Mysteries)",
        "bgm": "space",
        "description": "Mind-bending cosmic mysteries in Hindi: Black holes, neutron stars, time dilation in space, rogue wandering planets, cosmic radiation anomalies, boundaries of universe, James Webb telescope shock discoveries",
    },
    1: {  # Tuesday
        "niche": "ancient_engineering",
        "name": "प्राचीन भारत व विश्व के अजूबे (Impossible Ancient Megaliths & Architecture)",
        "bgm": "history",
        "description": "Impossible Ancient Engineering & Megaliths in Hindi: Kailasa Temple Ellora monolithic carving from single rock top-down, Giza Great Pyramids acoustic anomalies, Submerged Dwarka city, Tanjore Brihadeeswarar 80-ton granite dome, Lepakshi hanging pillar, Puma Punku precision stones",
    },
    2: {  # Wednesday
        "niche": "psychology",
        "name": "माइंड हैक्स व डार्क साइकोलॉजी (Dark Psychology & Brain Glitches)",
        "bgm": "auto",
        "description": "Dark psychology and human mind glitches in Hindi: Subconscious cognitive tricks, body language micro-expressions, manipulation defense, Mandela effect, eye movement lies detection, memory bugs",
    },
    3: {  # Thursday
        "niche": "ocean",
        "name": "गहरा समंदर व पाताल लोक (Deep Ocean Terrors & Earth Secrets)",
        "bgm": "space",
        "description": "Deep ocean abyss and earth secrets in Hindi: Mariana Trench sound anomalies, Point Nemo spacecraft graveyard, giant squid abyssal horrors, underwater toxic brine pools, mysterious subterranean caves",
    },
    4: {  # Friday
        "niche": "quantum_matrix",
        "name": "क्वांटम दुनिया व सिमुलेशन बग्स (Quantum Paradoxes & Simulation Reality)",
        "bgm": "space",
        "description": "Quantum paradoxes and simulation reality in Hindi: Time dilation traps where time moves differently, Quantum Zeno effect freezing particles, double-slit observer effect, simulation hypothesis real glitch proofs",
    },
    5: {  # Saturday - Tailored for Hindi Audience (Wild Animals Secrets & Superpowers)
        "niche": "animal_secrets",
        "name": "जानवरों के गुप्त रहस्य व सुपरपावर (Wild Animals Secrets & Biological Superpowers)",
        "bgm": "auto",
        "description": "Mind-blowing animal secrets and crazy biological superpowers in Hindi: Immortal jellyfish reversing aging, pistol shrimp punch creating sun surface heat shockwave, peregrine falcon 390 km/h dive speed vs cheetah, honey badger venom immunity, tardigrades surviving vacuum of space, electric eel 860-volt shock, deep sea glowing vampire squid, predator bite force comparisons",
    },
    6: {  # Sunday
        "niche": "mystery",
        "name": "दुनिया के अनसुलझे रहस्य (Unsolved World Enigmas & Strange Phenomena)",
        "bgm": "history",
        "description": "Shocking global unsolved mysteries in Hindi: Bermuda Triangle vanishings, mysterious sound of Taos Hum, bizarre dancing plague of 1518, mysterious Green children of Woolpit, cursed objects and unexplained archaeological discoveries",
    },
}

DAY_WISE_NICHES = DAY_WISE_NICHES_EN

def get_day_wise_niche(weekday=None, language: str = "en") -> dict:
    import datetime
    if weekday is None:
        weekday = datetime.datetime.now().weekday()
    is_hindi = str(language or "").lower().startswith("hi")
    schedule = DAY_WISE_NICHES_HI if is_hindi else DAY_WISE_NICHES_EN
    return schedule.get(weekday % 7, schedule[0])

# Bilingual stop words for accurate semantic normalization
STOPWORDS: Set[str] = {
    # English fillers & auxiliaries
    "the", "a", "an", "in", "of", "and", "for", "is", "was", "that", "this",
    "with", "its", "it", "to", "on", "at", "by", "why", "how", "what", "who",
    "when", "where", "are", "be", "been", "from", "as", "into", "all", "your",
    "you", "our", "we", "they", "them", "their", "just", "more", "about",
    "than", "then", "there", "these", "those", "can", "will", "would", "could",
    # Hindi / Hinglish fillers
    "का", "की", "के", "में", "पर", "से", "और", "है", "था", "थी", "थे", "हैं",
    "को", "ने", "एक", "यह", "वह", "तो", "भी", "ही", "किया", "गया", "रहा", "रहे",
    "रही", "लिए", "तक", "वाले", "वाली", "वाला", "होता", "होती", "होते", "हुए",
    "क्या", "क्यों", "कैसे", "कहाँ", "कब", "कौन", "अपना", "अपनी", "अपने", "अगर",
    "या", "नहीं", "बारे", "पास", "कर", "दिया", "दिए", "हो", "पे"
}

# Canonical cross-language entities to detect same stories told in English vs Hindi
CANONICAL_ENTITIES = [
    # Bharat Vigyan / Temples
    {"kailasa", "ellora", "कैलास", "कैलासा", "एलोरा"},
    {"padmanabhaswamy", "vault b", "पद्मनाभस्वामी", "वॉल्ट बी", "तिजोरी"},
    {"iron pillar", "delhi pillar", "लौह स्तंभ", "कुतुब मीनार स्तंभ"},
    {"ram setu", "adam bridge", "राम सेतु", "नल नील"},
    {"lepakshi", "hanging pillar", "लेपाक्षी", "झूलता खंभा"},
    {"brihadeeswarar", "thanjavur", "बृहदेश्वर", "तंजावुर"},
    {"dwarka", "submerged city", "द्वारका", "समुद्र में डूबी द्वारका"},
    {"konark", "sun temple", "कोणार्क", "सूर्य मंदिर"},
    {"vimana", "vymaanika", "विमान", "प्राचीन विमान"},
    {"brahmastra", "ब्रह्मास्त्र"},
    {"mohenjo daro", "harappa", "मोहनजोदड़ो", "हड़प्पा"},
    {"ajanta", "अजंता"},
    {"varahamihira", "वराहमिहिर"},
    {"sushruta", "सुश्रुत"},

    # Space & Cosmic Mysteries
    {"great attractor", "ग्रेट अट्रैक्टर"},
    {"mariana trench", "mariana", "मारियाना ट्रेंच", "मारियाना"},
    {"bermuda triangle", "bermuda", "बरमूडा ट्रायंगल", "बरमूडा"},
    {"voynich", "वॉयनिच", "वोयनिच"},
    {"antarctica", "piri reis", "अंटार्कटिका", "पिरी रीस"},
    {"sphinx", "स्फिंक्स"},
    {"taured", "man from taured", "टॉरेड", "टौरेड"},
    {"flight 914", "pan american 914", "फ्लाइट 914"},
    {"dancing plague", "डांसिंग प्लेग"},
    {"roswell", "airl", "matilda", "रोसवेल", "एयरल", "मटिल्डा"},
    {"boltzmann brain", "बोल्ट्ज़मैन"},
    {"quantum eraser", "क्वांटम इरेज़र"},
    {"immortal jellyfish", "turritopsis", "अमर जेलीफिश"},
    {"alexandria", "lost library", "सिकंदरिया", "अलेक्जेंड्रिया"},
    {"antikythera", "एंटीकाइथेरा", "प्राचीन कंप्यूटर"},
    {"dyatlov", "द्यातलोव"},
]

# Rich, multi-faceted fallback pools (18 diverse topics per niche)
GITA_MOTIVATION_FALLBACKS = [
    "Bhagavad Gita: How to Work Without Being Controlled by the Result",
    "What the Gita Teaches About Fear of Failure and Starting Again",
    "The Meaning of Nishkama Karma in Everyday Life",
    "How the Gita Explains a Steady Mind During Difficult Times",
    "Krishna's Guidance to Arjuna: Acting Clearly When You Feel Confused",
    "A Gita-Inspired Way to Stop Comparing Your Journey With Others",
    "What Ancient Indian Wisdom Says About Discipline and Patience",
    "How to Turn Setbacks Into Learning Without Losing Your Peace",
    "Gita Life Lesson: Focus on the Next Right Action",
    "The Difference Between Desire, Duty and Attachment in the Gita",
    "How the Idea of Dharma Can Guide Difficult Decisions",
    "What the Upanishads Teach About Knowing Your Inner Self",
    "Chanakya Niti: Why Self-Control Matters More Than Empty Promises",
    "Ancient Wisdom on Speaking Less and Choosing Words Carefully",
    "How Reflection and Daily Practice Build a More Steady Mind",
    "A Scripture-Inspired Lesson on Patience, Courage and Responsibility",
    "What the Gita's Sthitaprajna Ideal Means in Modern Life",
    "A Practical Reflection on Karma, Effort and Emotional Balance",
]


NICHE_FALLBACKS = {
    "gita_motivation": GITA_MOTIVATION_FALLBACKS,
    "space": [
        "Why You Would Age Backwards Near A Supermassive Neutron Star",
        "The Rogue Planet Wandering Towards Our Solar System Unseen",
        "What If Earth Lost Gravity For Exactly 5 Seconds",
        "The Scariest Sound Ever Recorded In Deep Space By Deep Space Probes",
        "The Planet Where It Rains Molten Glass Sideways At 5000 MPH",
        "The Mystery Of The Boomerang Nebula The Absolute Coldest Place In Space",
        "What Would Truly Happen If A Micro Black Hole Entered Our Solar System",
        "The Great Attractor: The Invisible Entity Dragging Entire Galaxies Towards It",
        "The Diamond Planet 40 Light Years Away Valued At 26 Nonillion Dollars",
        "Why Time Actually Stops At The Event Horizon Of A Black Hole",
        "The Cosmic Web: Physical Evidence That Our Universe Is Inside A Giant Brain",
        "The Dark Matter Hurricane Currently Passing Through Earth Unnoticed",
        "What Lies In The Void Of Bootes: The Emptiest Place In The Known Universe",
        "The Methuselah Star That Appears Older Than The Universe Itself",
        "The Fast Radio Burst From Deep Space Repeating Exactly Every 16 Days",
        "What Happens When Two Supermassive Black Holes Collide At Speed Of Light",
        "The Dyson Sphere Mystery: What Alien Megastructure Surrounds Tabby's Star",
        "The Big Rip Paradox: How Phantom Energy Could Tear Space Atoms Apart",
        "The Magnetar Star That Released Energy In 0.1 Seconds Equal To 100,000 Years Of Our Sun",
        "The Cosmic Void Of Canes Venatici: A 1-Billion-Light-Year Hole Where Matter Does Not Exist",
        "The Hellish Exoplanet K2-141b Where Ocean Is Made Of Liquid Rock And It Rains Supersonic Pebbles",
        "The Interstellar Wanderer Oumuamua: The Cigar-Shaped Cosmic Visitor Accelerating Without Gas",
        "The Diamond Core Of White Dwarf BPM 37093 Crystallized Into Billions Of Trillion Carats",
        "The Ghost Galaxy Dragonfly 44: Made Of 99.99 Percent Invisible Dark Matter",
        "The Quadruple Gravitational Lens Splitting A Single Quasar Into 4 Clones In Space",
        "The Zombie Star That Refused To Die And Detonated In 5 Consecutive Supernovae",
        "The Cosmic Microwave Background Cold Spot: A Potential Collision Bruise With Another Universe",
    ],
    "science": [
        "What Actually Happens In Your Brain When You Experience Sudden Deja Vu",
        "The Bizarre Quantum Experiment Proving The Past Can Be Modified",
        "The Biological Glitch In The Immortal Jellyfish That Completely Reverses Aging",
        "Why Boiling Water Freezes Faster Than Cold Water (The Mpemba Paradox)",
        "What Existed In The Universe Exactly One Second Before The Big Bang",
        "The Quantum Zeno Effect: Why A Particle Never Changes If You Keep Watching It",
        "The Double-Slit Experiment Anomaly: How Consciousness Alters Physical Matter",
        "Why All Solid Objects Around You Are Actually 99.999% Empty Space",
        "The Tachyonic Paradox: What Happens If Information Travels Faster Than Light",
        "The Neurological Reason Why Human Beings Cannot Imagine A Brand New Color",
        "How Synthetic DNA Could Store The Entire World's Internet In A Single Teaspoon",
        "The Antimatter Asymmetry: Why Did Matter Win The Big Bang Annihilation War",
        "Absolute Zero Glitch: The Bizarre State Of Matter Known As Bose-Einstein Condensate",
        "The Non-Newtonian Physics Of Oobleck: Liquid That Turns Into Armor Under Stress",
        "Why Gravity Is Trillions Of Times Weaker Than All Other Fundamental Forces",
        "The Time Dilation In Near-Death States: Why Dying Brains Slow Down Seconds Into Hours",
        "The Spooky Action At A Distance: Quantum Entanglement Verified Over 1200 Kilometers",
        "Schrodinger's Living Paradox: Real Quantum Superposition Observed In Lab Atoms",
    ],
    "bharat_vigyan": [
        "Kailasa Temple Ellora: How Ancient Architects Carved 400,000 Tons Of Basalt Top-Down",
        "Padmanabhaswamy Vault B: The Secret Acoustic Lock And Sacred Serpent Mystery",
        "Delhi Iron Pillar: The 1600-Year Rustproof Metallurgy Modern Science Cannot Replicate",
        "Ram Setu Floating Stones: The Geological Porosity And Ancient Acoustic Resonance",
        "Lepakshi Hanging Pillar: The Defiance Of Gravity That British Engineers Failed To Move",
        "Brihadeeswarar Temple: How An 80-Ton Granite Dome Was Hoisted Without Modern Cranes",
        "Dwarka: The 9000-Year-Old Submerged City Discovered Off The Coast Of Gujarat",
        "Konark Sun Temple: The Giant Magnetic Keystones That Steered Ancient Sea Ships",
        "The Musical Pillars Of Vittala Temple Hampi: Seven Musical Swaras Carved In Granite",
        "Sushruta Samhita: How Complex Rhinoplasty Was Performed In India 2600 Years Ago",
        "Vimana Shastra: The Mercury Vortex Propulsion Manuscripts Of Ancient Bharat",
        "The Underground Inverted Architecture Of Rani Ki Vav Built For Water Geometry",
        "Varahamihira: The Ancient Indian Sage Who Located Groundwater Using Termite Mounds",
        "The 1000-Year-Old Lost Wax Casting Of Chola Bronze That Never Rusts",
        "The Lost Saraswati River: Satellite Imagery Proving The 10000-Year Vedic Waterway",
        "The Jantar Mantar Samrat Yantra: Measuring Shadow Time Accurate To 2 Seconds",
        "The Vedic Calculation Of The Speed Of Light Hidden In Ancient Shlokas",
        "The Ajanta Caves Whispering Chambers: Acoustic Amplification Carved In Solid Lava Rock",
        "Puri Jagannath Temple Flag Anomaly: Why The Sacred Dhwaja Always Flutters Against Sea Wind",
        "Somnath Temple Baan Stambh: The Arrow Pillar Marking An Unobstructed Sea Path To Antarctica",
        "Meenakshi Amman Temple: The 33,000 Intricate Sculptures And Ancient Acoustic 1000 Pillar Hall",
        "Chand Baori Abhaneri: The 3500 Geometric Steps Built 1200 Years Ago Staying 5 Degrees Cooler",
        "Mahabalipuram Krishna Butterball: The 250-Ton Boulder Defying Gravity On A 45 Degree Slope",
        "Kedarnath Temple 2013 Flood Anomaly: The Giant Protective Rock Bheem Shila Miraculous Shield",
        "Golconda Fort Acoustic Whisper: A Handclap At The Outer Gate Heard 1 Kilometer Away",
        "Modhera Sun Temple: Designed So The Equinox Sun Directly Illuminates The Sacred Sanctum",
        "Belur Channakeshava Temple: The 12th Century Micro-Carved Lathe-Turned Soapstone Pillars",
    ],
    "glitch_matrix": [
        "The Man From Taured: The 1954 Traveler From A Country That Never Existed",
        "Pan American Flight 914: The Plane That Landed 37 Years After Scheduled Takeoff",
        "The Green Children Of Woolpit: The 12th Century Mystery From A Subterranean Realm",
        "The Simulation Hypothesis: Physicists Uncover Error-Correcting Code In Quantum Reality",
        "The Mandela Effect Patch Note: Proof That Alternate Realities Crossed In 2012",
        "The Object Duplication Glitch: Physical Relics Appearing Simultaneously In Two Places",
        "The 11 Missing Days Of September 1752: Why The Calendar Simply Skipped Forward",
        "The Time Slip At Versailles: Two Oxford Academics Who Walked Into 1789 France",
        "The 1977 Wow Signal: The 72-Second Frequency Burst From A Void Constellation",
        "The Vanishing Village Of Lake Anjikuni: 2000 Inhabitants Erased Overnight In 1930",
        "The Quantum Immortality Paradox: Why Your Consciousness Might Never Experience Death",
        "The Semantic Satiation Glitch: How A Common Word Dissolves Into Gibberish In 30 Seconds",
        "The Phantom Island Of Bermeja: The Landmass Erased From Mexican Sea Charts",
        "The Disappearance Of Flight MH370: The Modern Era's Most Haunting Sky Anomaly",
        "The Holographic Universe Principle: Are We Merely 2D Projections On A Cosmic Boundary",
        "The Anecdotal Time Jumps: Hikers Experiencing 3-Day Hikes In Just 40 Minutes",
        "The Shared Hallucination Mystery: Hundreds Seeing Identical Anomalies Simultaneously",
        "The Double Memory Glitch: Why You Remember Two Completely Different Childhood Homes",
    ],
    "psychology": [
        "The Inception Loop: A Dark Psychology Trick To Plant A Thought In Someone's Mind",
        "3 Subtle Facial Micro-Twitches That Instantly Reveal If Someone Is Deceiving You",
        "The Ben Franklin Effect: How Asking For A Tiny Favor Turns Rivals Into Allies",
        "The Bystander Paralysis: Why Large Crowds Freeze And Refuse To Intervene In Danger",
        "Why Total Silence Is The Most Terrifying Weapon In Any Hostile Negotiation",
        "The Spotlight Illusion: Why Practically Nobody Notices Your Awkward Social Blunders",
        "The Pratfall Effect: Why Small Imperfections Make Charismatic People More Liked",
        "The Door-In-The-Face Technique: How To Ensure Anyone Agrees To Your True Request",
        "The Pygmalion Effect: How Expecting Excellence Rewires Human Potential",
        "Why Toxic Personalities Reflexively Accuse You Of Their Own Secret Flaws",
        "The Cognitive Dissonance Trap: Why People Defend Clearly Broken Beliefs",
        "The Zeigarnik Effect: Why Your Subconscious Brain Refuses To Forget Unfinished Chores",
        "How Involuntary Pupil Dilation Instantly Reveals Emotional Attraction",
        "The Halo Effect: Why People Subconsciously Equate Attractiveness With Morality",
        "The Sunk Cost Fallacy: Why Humans Cling To Sinking Ships And Poisonous Situations",
        "The Chameleon Effect: Why Subconsciously Mirroring Posture Instantly Builds Trust",
        "The Anchoring Bias: How Supermarkets Trick Your Brain Into Spending Three Times More",
        "The Dunning-Kruger Trap: Why Incompetent People Are Absolutely Convinced They Are Right",
    ],
    "mystery": [
        "The 500-Year-Old Piri Reis Map Depicting Antarctica Free Of Ice Caps",
        "Deep Sea Sonar Just Detected A Colossal Artificial Megastructure In Mariana Trench",
        "The Voynich Manuscript: The 15th Century Herbal Codices No Cryptographer Can Crack",
        "The Lost Underground Labyrinth Of Hawara: 3000 Underground Chambers Beneath Egypt",
        "The Eye Of The Sahara (Richat Structure): The Physical Coordinates Of Lost Atlantis",
        "The Baltic Sea Disc Anomaly: The Object That Neutralizes Sonar And Radio Signals",
        "The Giant Siberian Sinkholes Erupting Overnight Across The Arctic Permafrost",
        "The Yonaguni Megaliths: Underwater Steps And Terraces In Japan Defying Geology",
        "The 1000-Year-Old Longyou Caves: Hand-Carved Subterranean Chambers Under China",
        "The Mount Kailash Pyramid Mystery: Why Mountain Climbers Age Rapidly Near Its Base",
        "The Georgia Guidestones Monolith: The Mysterious Sender And The 1980 Warning",
        "The Oak Island Money Pit: The Self-Flooding Booby Trap Guarding Ancient Treasure",
        "The Taos Low-Frequency Hum: The Drone Tormenting An Entire New Mexico Valley",
        "The Antikythera Mechanism: The 2100-Year-Old Greek Clockwork Analog Computer",
        "The Lost Legion Of Crassus: Thousands Of Roman Soldiers Who Disappeared In Ancient China",
        "Gobekli Tepe Megaliths: 12000-Year-Old Carved Temples Built Before Agriculture",
        "The Devil's Kettle Falls: The River In Minnesota That Disappears Into An Infinite Abyss",
        "The Marfa Ghost Lights: Glowing Unexplained Plasma Orbs Floating Above The Desert",
    ],
    "history": [
        "The Roman Emperor Caligula Who Declared War On Neptune And Ordered Soldiers To Stab Waves",
        "The 1518 Dancing Plague Of Strasbourg: Hundreds Danced Uncontrollably Until Collapse",
        "The Lost Colony Of Roanoke: 115 Settlers Who Vanished Leaving A Single Cryptic Word",
        "The Bronze Age Collapse 1177 BC: How The Entire Civilized World Burned Down In 50 Years",
        "The Real Vlad The Impaler: The Psychological Night Attack That Horrified An Empire",
        "The Year Without A Summer 1816: How An Indonesian Volcano Froze The Entire Globe",
        "The 2400-Year-Old Greek Fire Weapon: The Burning Chemical Sea Weapon Water Could Not Extinguish",
        "The Secret Underground Library Of Ivan The Terrible Hidden Beneath The Moscow Kremlin",
        "The Ghost Army Of WWII: The Inflatable Phantom Tanks That Fooled Axis High Command",
        "The Boston Molasses Tidal Wave Of 1919: A 25-Foot Boiling Sticky Wave Engulfing Streets",
        "The 1859 Carrington Solar Superstorm: When Telegraph Lines Burst Into Flames Worldwide",
        "The Disappearance Of The Roman Ninth Legion In The Dense Mists Of Ancient Scotland",
        "The Tunguska Siberian Explosion Of 1908: The Mysterious Airburst That Leveled 80 Million Trees",
        "The Cataclysms Of Herculaneum: Citizens Preserved In Boiling Volcanic Mud For 2000 Years",
        "The Byzantine Sacred Icon That Secretly Saved Constantinople From A Sea Siege",
        "The Dancing War Planes Of The 1942 Battle Of Los Angeles Air Raid Over Midnight Skies",
        "The Strange Assassination Of Grigori Rasputin: The Siberian Mystic Who Survived Cyanide",
        "The 1932 Australian Great Emu War: When Royal Artillery Failed Against Flightless Birds",
    ],
    "ocean": [
        "Deep Sea Hydrophones Just Detected A Terrifying Ultra-Low Resonance (The Bloop)",
        "Point Nemo: The Deep Ocean Spacecraft Graveyard And The Loneliest Point On Earth",
        "The Dragon's Triangle: The Pacific Ocean Anomaly Where Navies Disappear Without Trace",
        "The 45-Foot Colossal Squid: The Leviathan Of The Deep Hunting Sperm Whales In The Dark",
        "The Deep Sea Brine Pools Of Doom: Underwater Lakes That Kill Any Creature Entering Them",
        "The Lost Sunken Metropolis Of Thonis-Heracleion Found Submerged In Mediterranean Mud",
        "The Mariana Trench 36000-Foot Plastic Glitch: Manmade Garbage Discovered In Earth's Deepest Scar",
        "Megalodon Fossil Teeth Found In Fresh Abyssal Silt: Are Apex Predators Still Down There",
        "The Underwater Black Smokers: Hydrothermal Chimneys Thriving Without Any Sunlight",
        "The Great Blue Hole Stalactites: Geological Proof That The Ocean Abyss Was Once Dry Land",
        "The USS Scorpion Nuclear Submarine Tragedy: What Secretly Torpedoed It In 1968",
        "The Mariana Hadal Snailfish: Surviving 1000 Times Atmospheric Pressure In Freezing Waters",
        "The Glowing Milky Sea Phenomenon: 100 Miles Of Luminous Ocean Visible From Satellite Orbit",
        "The Bimini Road: Submerged Geometric Stone Blocks Off The Bahamas Resembling Ancient Highways",
        "The Devil's Sea Mystery: What Caused The Sudden Sinking Of The Kaio Maru Research Vessel",
        "The Azores Underwater Pyramid: A 60-Meter Submerged Structure Discovered By Local Fishermen",
        "The Giant Maelstrom Of Saltstraumen: The World's Deadliest Underwater Whirlpool Trap",
        "The Challenger Deep Sonar Echo: Mysterious Dense Mass Moving Along The Deepest Trench Wall",
    ],
    "ai_future": [
        "What Happens If An Artificial Superintelligence Silently Achieves Self-Awareness",
        "The Dead Internet Theory: Are Over 70 Percent Of Online Profiles Autonomous Neural Bots",
        "The Neural Lace Security Breach: Can Bad Actors Remotely Hack Your Human Memories",
        "The Quantum Computing Cryptography Apocalypse: When All Global Bank Codes Break In Minutes",
        "The AI Hallucination Glitch: Why Giant Machine Learning Models Fabricate Alternate History",
        "Roko's Basilisk Thought Experiment: The Information Hazard In Autonomous Artificial Ethics",
        "What Human Genomic Sequences Will Look Like After 500 Years Of CRISPR Gene Rewrites",
        "The Autonomous Drone Swarm Warfare: Algorithms Making Lethal Target Choices Without Humans",
        "The Mind Uploading Ship Of Theseus: Would A Digital Clone Ever Possess Your Real Consciousness",
        "The Bloodstream Nanobot Revolution: Microscopic Robots Repairing Human Arteries From Inside",
        "The 2045 Technological Singularity: When Machine Intelligence Forever Outstrips Human Reason",
        "The Biometric Panopticon: How City Street Cameras Read Micro Facial Emotion In Milliseconds",
        "The Deepfake Audio Crisis: When Voice Authentication And Phone Calls Can Never Be Trusted",
        "Quantum Teleportation Verified Over 30 Miles: Moving Information Instantly Without Crossing Space",
        "The Autonomous Bot Language Drift: Two Communicating AIs Developing Their Own Private Cipher",
        "The Synthetic Biology Hazard: Assembling Functional Living Organisms From Scratch In Test Tubes",
        "The Brain-Machine Telepathy Test: Two Patients Transmitting Mental Commands Across The Internet",
        "The Artificial Memory Implantation Trial: How Neuroscientists Planted A False Memory In Living Brains",
    ],
    "conspiracy": [
        "The Guy Hottel FBI Memo: The 1950 Declassified Official Hoover Memo On Three Flying Discs",
        "Project Stargate: The CIA Declassified Remote Viewing Program Targeting Ancient Martian Coordinates",
        "Project MKUltra: The Declassified Government Mind Experiments Inside Major American Hospitals",
        "Operation Northwoods: The 1962 Classified False Flag Proposal Unanimously Rejected By The President",
        "Cheyenne Mountain Super-Bunker: The Underground Military City Built Inside Solid Granite",
        "The Svalbard Global Vault: Why World Powers Buried 1 Million Crop Seeds Beneath Polar Ice",
        "The Denver International Airport Underground Tunnels And The Freemason Time Capsule Murals",
        "Project Blue Book Special Report 14: Over 3200 Declassified Unexplained Military Encounters",
        "The Varginha 1996 Incident: The Brazilian Crash And The Military Quarantine Of A Living Extraterrestrial",
        "The Rendlesham Forest 1980 UFO Event: When USAF Officers Touched A Hieroglyphic Craft",
        "The Apollo 11 Two-Minute Transmission Blackout: What Neil Armstrong Really Reported From The Moon",
        "The CIA Gateway Process Analysis: Escaping Three-Dimensional Spacetime Through Hemispheric Brain Sync",
        "Project Iceworm: The Secret US Nuclear Missile Launch Network Buried Beneath Greenland's Ice Sheet",
        "The Malmstrom Air Force Base Anomaly: 10 Minuteman Nuclear Missiles Mysteriously Deactivated By A Red Orb",
        "The Philadelphia Naval Experiment: The Truth Behind The USS Eldridge Electromagnetic Cloaking Legend",
        "The Area 51 S4 Whistleblower Accounts: Element 115 And Gravity-Wave Waveguide Reactors",
        "The Pine Gap Top Secret Facility: The Joint Australian-US Signals Intercept Super-Station",
        "The Kecksburg 1965 Acorn Crash: The Metallic Object Transported Under Military Guard At Night",
    ],
    "cartoon": [
        "Cute Golden Retriever Puppy Secretly Operating A Midnight Bakery For Woodland Animals",
        "Mischievous Baby T-Rex Trying To Sneak A Giant Glazed Doughnut Out Of A Prehistoric Kitchen",
        "Quirky Little Broken Robot Trying To Teach A Fluffy Kitten How To Be A City Superhero",
        "Adorable Fluffy White Bunny Who Stumbles Upon A Glowing Rainbow Underground Carrot",
        "Grumpy Old Wizard Owl Forced To Babysit Five Hyperactive Baby Flying Squirrels",
        "Tiny Dragon Who Hiccups Bubbles Instead Of Fire Learning To Defend His Golden Cave",
        "Clever Little Hamster Engineering A Cardboard Rocket Ship To Visit The Moon Made Of Cheese",
        "Curious Baby Giant Panda Tumbling Down A Bamboo Forest And Making Wild Forest Friends",
        "Sneaky Black Cat Detective In A Tiny Trenchcoat Solving The Case Of The Missing Kitchen Fish",
        "Clumsy Baby Emperor Penguin Trying To Learn Figure Skating With An Overzealous Walrus Coach",
        "Playful Golden Puppy Convinced His Own Shadow Is A Magical Invisible Playmate",
        "Tiny Forest Hedgehog Waking Up To Discover His Spikes Glow In Radiant Neon Colors",
        "Sweet Little Brown Bear Cub Baking The Forest's Tallest Pancake Stack With Bluebirds",
        "Sleepy Sloth Who Accidentally Stumbles Onto The Running Track And Wins The Animal Marathon",
        "Cheerful Tiny Clockwork Robot Delivering Whimsical Letters Across A Fairy-Tale Forest Town",
        "Baby Elephant Who Learns To Soar High In The Clouds Using His Massive Ears As Wings",
        "Adventurous Ginger Kitten Stowing Away Inside A Toy Spaceship On A Living Room Odyssey",
        "Funny Rainbow Chameleon Who Keeps Accidentally Changing Color Whenever He Tells A Little Lie",
    ],
    "mythology": [
        "The Ancient Brahmastra: The First Described Weapon Of Mass Atomic Destruction In Epic Texts",
        "The Secret 7th Vault Of Padmanabhaswamy Temple Sealed With The Naga Bandham Mantra",
        "The Unbelievable Architectural Geometry Of Kailasa Temple Carved Out Of A Single Mountain Peak",
        "The Flying Vimanas Of Ancient India: Mercury Vortex Propulsion Described In Ancient Manuscripts",
        "The Hidden Sanjeevani Herb: The Ancient Bio-Luminescent Plant Connected To Modern Cellular Science",
        "The Celestial Astras Of The Mahabharata: Guided Sonic And Plasma Weaponry In Ancient Times",
        "The Lost Golden City Of Dwarka Found Under Arabian Sea: 36 Years After The Mahabharata War",
        "The Agastya Samhita Battery: Ancient Battery Formula That Generated Electric Charge In Vedic Times",
        "The Churning Of The Ocean (Samudra Manthan): The Cosmic Chemistry Metaphor In Sacred Texts",
        "The Mysterious Sonic Resonance In The Ancient Vedic Chants That Matches Cosmic Microwave Background",
        "The Impossible Architecture Of Lepakshi Hanging Pillar That Defies Modern Gravitational Laws",
        "The Sudarshana Chakra: The Supreme Cosmic Discus With Unstoppable Kinetic Energy",
    ],
    "animal_secrets": [
        "The Pistol Shrimp Bullet Blast: How A Tiny Claw Creates Sun-Level Heat Underwater",
        "The Peregrine Falcon vs Cheetah: Why Diving At 390 KMH Defies Physics",
        "The Immortal Jellyfish: The Biological Glitch That Reverses Aging Forever",
        "The Honey Badger's Immunity: Surviving Deadly King Cobra Venom After A Two-Hour Nap",
        "The Axolotl's Regrowth Mystery: Growing A Brand-New Heart And Brain In Weeks",
        "The Tardigrade Space Survivor: Surviving Absolute Vacuum And Lethal Cosmic Radiation",
        "The Electric Eel's 860-Volt Shockwave: Stun Power That Can Paralyze A Caiman",
        "The Mantis Shrimp Punch: Accelerating At The Speed Of A 22-Caliber Bullet",
        "The Harpy Eagle Talon Power: Crushing Skulls With More Force Than A Rottweiler",
        "The Lyrebird Voice Mimicry: The Bird That Perfectly Copies Chainsaws And Car Alarms",
        "The Wood Frog Deep Freeze: Heart Completely Stops In Winter And Restarts In Spring",
        "The Saltwater Crocodile Bite Force: 3700 Pounds Of Pure Prehistoric Crushing Power",
        "The Golden Poison Dart Frog: One Drop Of Skin Toxin Enough To Stop 10 Hearts",
        "The Mimic Octopus Transformation: Shapeshifting Into 15 Different Marine Predators",
        "The Bombardier Beetle Chemical Cannon: Blasting Boiling Acid Spray At 100 Degrees Celsius",
        "The Albatross Non-Stop Flight: Gliding Across Oceans For Six Years Without Touching Ground",
        "The Cuttlefish Hypnotic Skin Strobe: Flashing Lights That Freeze Prey In Place",
        "The Inland Taipan Neurotoxin: The World's Deadliest Snake Venom Explained",
    ],
    "ancient_engineering": [
        "The 1200-Year-Old Kailasa Temple Carved Completely Out Of A Single Mountain From Top Down",
        "The 2000-Year-Old Antikythera Mechanism: Why An Ancient Analog Computer Shocked Modern Science",
        "The 12000-Year-Old Megalithic Site Of Gobekli Tepe That Rewrote Human History",
        "The Bizarre Thermal Anomaly Inside The Great Pyramid Of Giza Scientists Cannot Explain",
        "Puma Punku's Impossible Precision Cut Granite Blocks That Modern Tools Cannot Replicate",
        "The Underground Megacity Of Derinkuyu Built 18 Floors Deep To Escape An Unknown Threat",
        "The Submerged 9000-Year-Old Ruins Of Dwarka Found Off The Coast Of Gujarat",
        "The 1600-Year-Old Iron Pillar Of Delhi That Defies Rust And Modern Metallurgy",
        "The Acoustic Gravity Secrets Behind The 80-Ton Granite Dome Of Brihadeeswarar Temple",
        "The Lepakshi Hanging Pillar That Floats Millimeters Above The Stone Floor Without Support",
        "The 20000-Year-Old Yonaguni Submarine Monument That Defies Natural Geology",
        "The Impossible Polygonal Stone Masonry In Peru That Withstands Massive Earthquakes",
        "The Ancient Unmeltable Crystal Skulls Carved Against The Natural Grain Of Quartz",
        "The Padmanabhaswamy Temple Vault B Sealed With Ancient Acoustic Snake Frequencies",
        "The 500-Year-Old Piri Reis Map That Depicts An Ice-Free Antarctica Coastline",
        "The Mysterious Sonic Levitating Stone Legends Behind Ancient Monolithic Temples",
        "The Secret Under-Sphinx Chamber Blocked By Water And Classified Egyptian Permits",
        "The Mohenjo-Daro Vitrified Ruins And Ancient Radioactive Anomalies",
    ],
    "quantum_matrix": [
        "The Quantum Zeno Effect: Why An Atom Literally Freezes In Time When You Watch It",
        "The Time Dilation Trap: Why Your Head Is Technically Older Than Your Own Feet",
        "The Boltzmann Brain Paradox: Why You Might Just Be A Spontaneous Hallucination In The Void",
        "Vacuum Decay: The Cosmic Bubble Expanding At Light Speed That Deletes The Universe",
        "The Double-Slit Experiment Anomaly: Physical Matter Behaving Differently When Observed",
        "The Delayed-Choice Quantum Eraser That Proves Your Present Decision Changes The Past",
        "Why All Solid Matter Around You Is Actually 99.9999 Percent Completely Empty Space",
        "The Mandela Effect Patch Notes: Physical Proofs The Reality OS Was Updated",
        "The Man From Taured: The Traveler Who Landed With A Passport From A Non-Existent Nation",
        "The Quantum Immortality Paradox: Why Your Consciousness Might Never Experience Death",
        "Pan American Flight 914: The 1955 Plane That Landed In Caracas 37 Years Later",
        "The Semantic Satiation Glitch: How The Human Brain Forgets A Word Meaning In 30 Seconds",
        "The Truman Show Delusion: Why Thousands Believe Their Lives Are A Secret Global Broadcast",
        "The Simulation Boundary: Why The Speed Of Light Is The Processor Clock Limit Of Reality",
        "The Fast Radio Burst From Deep Space Repeating On An Exact Mathematical Clockwork Cycle",
        "The Quantum Entanglement Spooky Action: Two Particles Telepathically Linked Across Galaxies",
        "The 1989 Sky Glitch Where An Entire City Experienced A Sudden 2-Minute Time Slip",
        "Why Physicists Suspect We Are Living Inside The Inner Event Horizon Of A Black Hole",
    ],
}


NICHE_FALLBACKS_HI = {
    "ancient_engineering": [
        "एलोरा का कैलाश मंदिर: ऊपर से नीचे की ओर एक ही चट्टान को तराश कर बनाया गया अजूबा!",
        "प्राचीन स्तूपों की 1500 साल पुरानी सेल्फ-कूलिंग ईंटें: 95% गर्मी सोखने वाली गुप्त तकनीक!",
        "दिल्ली का 1600 साल पुराना लौह स्तंभ: जिस पर आज तक जंग क्यों नहीं लगी?",
        "तंजौर का वृहदेश्वर मंदिर: 80 टन के ग्रेनाइट गुंबद को शिखर पर कैसे स्थापित किया गया?",
        "लेपाक्षी का झूलता हुआ खंभा: जो जमीन को छुए बिना हवा में लटका हुआ है!",
        "गुजरात के तट पर डूबी 9000 साल पुरानी द्वारका नगरी का पुरातात्विक रहस्य!",
        "तुर्की की 18 मंजिला भूमिगत नगरी डेरिंकुयु: जमीन के नीचे 20,000 लोगों का शहर!",
        "गीज़ा के पिरामिडों के भीतर का थर्मल एनोमली: वैज्ञानिक आज भी हैरान क्यों हैं?",
    ],
    "bharat_vigyan": [
        "एलोरा का कैलाश मंदिर: 1200 साल पुरानी वास्तुकला जो आज भी आधुनिक विज्ञान को चुनौती देती है!",
        "पद्मनाभस्वामी मंदिर का सातवां तहखाना: जिसे प्राचीन नाग बंधम मंत्र से सील किया गया है!",
        "राम सेतु के तैरते पत्थरों का भूवैज्ञानिक और ध्वनि तरंग विज्ञान!",
        "प्राचीन भारत का वूट्ज स्टील: जिससे दमिश्क की अटूट तलवारें बनाई जाती थीं!",
        "सुश्रुत संहिता: 2600 साल पहले भारत में की गई पहली प्लास्टिक सर्जरी का इतिहास!",
        "वराहमिहिर और आर्यभट्ट का खगोल विज्ञान: गुरुत्वाकर्षण और ग्रहों की सटीक गणना!",
    ],
    "animal_secrets": [
        "अमर जेलीफ़िश: जो कभी बूढ़ी नहीं होती और अपनी उम्र को उल्टा घुमा लेती है!",
        "पेरेग्रीन बाज़ की 390 किमी/घंटा डाइव स्पीड: चीते से 3 गुना तेज उड़ने वाली सुपरपावर!",
        "पिस्तौल झींगा: जिसका एक झटका पानी के अंदर सूरज जितनी गर्मी पैदा करता है!",
        "हनी बैजर की अद्भुत प्रतिरोधक क्षमता: किंग कोबरा के जानलेवा जहर को भी पचाने वाला जीव!",
        "एक्सोलोटल का जैविक चमत्कार: जो कुछ ही हफ्तों में अपना दिल और दिमाग दोबारा उगा लेता है!",
        "टार्डिग्रेड: जो अंतरिक्ष के शून्य और जानलेवा रेडिएशन में भी 30 साल जिंदा रह सकता है!",
        "इलेक्ट्रिक ईल का 860 वोल्ट करंट: जो मगरमच्छ को भी एक झटके में बेहोश कर दे!",
        "मिमिक ऑक्टोपस: जो पलक झपकते ही 15 अलग-अलग समुद्री शिकारियों का रूप बदल लेता है!",
    ],
    "space": [
        "अंतरिक्ष का वह भयानक गड्ढा: जहां लाखों प्रकाश वर्ष तक कोई तारा या गैलेक्सी मौजूद नहीं है!",
        "डायमंड प्लैनेट 55 कैनक्री ई: जो पूरा का पूरा शुद्ध हीरे और ग्रेफाइट से बना हुआ है!",
        "न्यूट्रॉन स्टार का भयानक घनत्व: जिसके एक चम्मच पदार्थ का वजन माउंट एवरेस्ट जितना होता है!",
        "ग्रेट अट्रैक्टर: वह अदृश्य शक्ति जो हमारी पूरी आकाशगंगा को अपनी ओर खींच रही है!",
        "बोमरैंग नेबुला: ब्रह्मांड की वह जगह जो अंतरिक्ष के सामान्य तापमान से भी ज्यादा ठंडी है!",
        "ब्लैक होल का इवेंट होराइजन: जहां पहुंचकर समय हमेशा के लिए पूरी तरह थम जाता है!",
    ],
    "quantum_matrix": [
        "क्वांटम ज़ेनो इफ़ेक्ट: किसी कण को लगातार देखने पर उसका समय कैसे रुक जाता है?",
        "टाइम डाइलेशन का चक्रव्यूह: आपके सिर की उम्र आपके पैरों से ज्यादा तेज क्यों बढ़ती है?",
        "डबल स्लिट प्रयोग का रहस्य: क्या चेतना भौतिक पदार्थ के व्यवहार को बदल देती है?",
        "बोल्ट्ज़मैन ब्रेन का विरोधाभास: क्या यह पूरी दुनिया महज एक क्षणिक भ्रम है?",
        "समय की गति की सीमा: प्रकाश की गति इस ब्रह्मांड के प्रोसेसर की लिमिट क्यों मानी जाती है?",
    ],
    "glitch_matrix": [
        "टॉरेड का वह अज्ञात यात्री: जो 1954 में एक ऐसे देश का पासपोर्ट लेकर आया जो धरती पर था ही नहीं!",
        "पैन अमेरिकन फ्लाइट 914: 1955 में उड़े विमान का 37 साल बाद कराकस में उतरने का सच!",
        "डेजा वू का न्यूरोलॉजिकल रहस्य: क्या हमारा मस्तिष्क पहले से जी चुकी घटना को याद करता है?",
        "मंडेला इफ़ेक्ट: जब करोड़ों लोगों को इतिहास की एक जैसी झूठी घटना याद रहने लगे!",
    ],
    "psychology": [
        "मानव मस्तिष्क का अजीबोगरीब खेल: इंसान कभी कोई नया रंग क्यों नहीं सोच सकता?",
        "डार्क साइकोलॉजी और बॉडी लैंग्वेज: किसी के झूठ को 5 सेकंड में पकड़ने का तरीका!",
        "सबकॉन्शियस माइंड की प्रोग्रामिंग: नींद में हमारा दिमाग क्या सीखता है?",
        "प्लेसबो इफ़ेक्ट की रहस्यमयी ताकत: जब खाली चीनी की गोली से बड़ी-बड़ी बीमारियां ठीक हो जाती हैं!",
    ],
    "mystery": [
        "मारियाना ट्रेंच की 36,000 फीट की गहराई: जहां आज भी अजीबोगरीब विशालकाय आकृतियां देखी जाती हैं!",
        "वॉयनिच पांडुलिपि: 600 साल पुरानी वह रहस्यमयी किताब जिसे आज तक कोई वैज्ञानिक नहीं पढ़ पाया!",
        "अंटार्कटिका की बर्फ के 2 मील नीचे दबी झील वोस्तोक का रहस्य!",
        "बरमूडा ट्रायंगल की मैग्नेटिक एनोमली: जहां कंपास अचानक दिशा भूल जाते हैं!",
    ],
    "gita_motivation": [
        "श्रीमद्भगवद्गीता: कर्म के फल की चिंता किए बिना श्रेष्ठ कर्म कैसे करें?",
        "श्रीकृष्ण का अर्जुन को उपदेश: जब मन में गहरा संशय हो तो सही निर्णय कैसे लें?",
        "स्थितप्रज्ञ का लक्षण: सुख और दुख में समभाव रखने की प्राचीन कला!",
        "निष्काम कर्म योग: आधुनिक तनाव और बेचैनी से मुक्ति पाने का वैदिक मार्ग!",
    ],
    "ocean": [
        "मारियाना ट्रेंच की अतल गहराइयां: धरती के सबसे गहरे गड्ढे में क्या छिपा है?",
        "पॉइंट नीमो: अंतरिक्ष से भी दूर समुद्र का वह कोना जहां कोई इंसान नहीं रहता!",
        "विशालकाय कोलोसल स्क्विड: गहरे समुद्र में रहने वाला वह महाकाय दैत्य!",
        "समुद्र के भीतर बनी रहस्यमयी खारे पानी की झीलें: जहां जाने वाला जीव कभी वापस नहीं आता!",
    ],
}


SCRIPTURE_TOPIC_MARKERS = (
    "bhagavad gita", "bhagwat gita", "gita", "geeta", "granth", "scripture",
    "shloka", "shlok", "upanishad", "chanakya niti", "sanatan", "spiritual",
    "vedic scripture", "karma yoga", "nishkama karma",
)
SCRIPTURE_DEVANAGARI_MARKERS = (
    "गीता", "ग्रंथ", "ग्रन्थ", "शास्त्र", "श्लोक", "उपनिषद", "चाणक्य नीति",
    "सनातन", "आध्यात्म", "कर्मयोग", "निष्काम कर्म", "वेद",
)


def _ensure_scripture_topic_identity(niche: str, topics: List[str]) -> List[str]:
    """Retain a sacred-text marker so script, voice and visual routing remain consistent."""
    if niche != "gita_motivation":
        return topics
    tagged: List[str] = []
    for topic in topics:
        text = str(topic).strip()
        lowered = text.lower()
        has_marker = (
            any(re.search(rf"\b{re.escape(term)}\b", lowered) for term in SCRIPTURE_TOPIC_MARKERS)
            or any(term in lowered for term in SCRIPTURE_DEVANAGARI_MARKERS)
        )
        tagged.append(text if has_marker else f"Ancient Scripture Wisdom: {text}")
    return tagged


class TrendFinder:
    """Discovers viral, high-retention topics and guarantees zero repetition with multi-factor deduplication."""

    def __init__(self):
        self.cfg = get_config()
        self.history_file = HISTORY_FILE
        self._ensure_history_file()
        self.session_used_topics: Set[str] = set()

    def _ensure_history_file(self):
        if not self.history_file.exists():
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump({"topics": [], "video_ids": []}, f, indent=2, ensure_ascii=False)

    def get_day_wise_niche(self, weekday=None, language: str = "en") -> dict:
        """Return the day-wise theme dictionary for the specified weekday and target audience language."""
        return get_day_wise_niche(weekday=weekday, language=language)

    def resolve_niche(self, raw_niche: str, language: str = "en") -> Tuple[str, str]:
        """Map any free-form slot niche string to a canonical key and rich prompt description."""
        raw_lower = raw_niche.lower().strip()
        # Daily Mirror & Day-Wise automatic theme rotation
        daily_rotation_triggers = (
            "daily_mirror", "daily_theme", "day_wise", "day-wise", "daily_schedule",
            "auto_day", "daily", "daily rotating", "rotating", "rotation", "rotate",
            "dynamic", "theme of the day", "har din alag", "alag topic", "daily rotate"
        )
        if any(trig in raw_lower for trig in daily_rotation_triggers):
            day_data = get_day_wise_niche(language=language)
            return day_data["niche"], day_data["description"]
        # Explicit scripture-topic routing comes before the broad substring map.
        # Latin terms use word boundaries so "gita" does not accidentally match "digital".
        sacred_terms = (
            "bhagavad gita", "bhagwat gita", "gita", "geeta", "granth", "scripture",
            "shloka", "shlok", "upanishad", "chanakya niti", "sanatan", "spiritual",
            "karma yoga", "nishkama karma",
        )
        if any(re.search(rf"\b{re.escape(term)}\b", raw_lower) for term in sacred_terms) or any(
            term in raw_lower
            for term in ("गीता", "ग्रंथ", "श्लोक", "उपनिषद", "चाणक्य नीति", "सनातन", "आध्यात्मिक", "कर्मयोग", "निष्काम कर्म")
        ):
            return "gita_motivation", VIRAL_NICHES["gita_motivation"]

        # Direct lookup
        if raw_lower in VIRAL_NICHES:
            return raw_lower, VIRAL_NICHES[raw_lower]

        # Keyword mapping (use word boundaries for short <= 3 char words like 'ai' or 'sea')
        for keyword, canon_key in NICHE_KEYWORD_MAPPINGS.items():
            if len(keyword) <= 3 and keyword.isalpha():
                if re.search(rf"\b{re.escape(keyword)}\b", raw_lower):
                    return canon_key, VIRAL_NICHES.get(canon_key, VIRAL_NICHES["mystery"])
            elif keyword in raw_lower:
                return canon_key, VIRAL_NICHES.get(canon_key, VIRAL_NICHES["mystery"])

        # Default fallback
        return "mystery", f"{raw_niche}: Mind-bending viral mysteries, scientific enigmas, and shocking untold truths"

    def _normalize_topic(self, topic: str) -> str:
        """Unicode-safe normalization preserving Hindi/Devanagari matras, accented characters, and stripping fillers."""
        res = []
        for ch in topic.lower().strip():
            cat = unicodedata.category(ch)
            # Keep Letters (L*), Numbers (N*), Marks (M* - includes combining vowels/matras), and whitespace
            if cat.startswith(("L", "N", "M")) or ch.isspace():
                res.append(ch)
            else:
                res.append(" ")
        words = [w for w in "".join(res).split() if w not in STOPWORDS and len(w) > 1]
        return " ".join(words)

    def _get_canonical_entity_group(self, text: str) -> Optional[int]:
        """Detect if topic covers a canonical entity (to prevent cross-lingual duplicate stories)."""
        text_lower = text.lower()
        for idx, entity_set in enumerate(CANONICAL_ENTITIES):
            if any(term in text_lower for term in entity_set):
                return idx
        return None

    def _is_topic_similar(self, new_topic: str, existing_topics: List[str], threshold: float = 0.40) -> bool:
        """Multi-factor similarity check: exact match, normalized match, canonical entity, Jaccard, containment, SequenceMatcher."""
        clean_new = new_topic.strip().lower()
        if not clean_new:
            return True

        new_normalized = self._normalize_topic(new_topic)
        new_words = set(new_normalized.split())
        new_entity_grp = self._get_canonical_entity_group(new_topic)

        for existing in existing_topics:
            clean_exist = existing.strip().lower()
            if not clean_exist:
                continue

            # 1. Exact raw match
            if clean_new == clean_exist:
                return True

            # 2. Canonical cross-language entity match (e.g. Kailasa in English vs कैलाश in Hindi)
            if new_entity_grp is not None:
                exist_entity_grp = self._get_canonical_entity_group(existing)
                if exist_entity_grp == new_entity_grp:
                    return True

            existing_normalized = self._normalize_topic(existing)
            # 3. Exact normalized match
            if new_normalized and new_normalized == existing_normalized:
                return True

            # 4. Long substring containment (if length >= 12 chars and one is wholly inside the other)
            if len(new_normalized) >= 12 and len(existing_normalized) >= 12:
                if new_normalized in existing_normalized or existing_normalized in new_normalized:
                    return True

            existing_words = set(existing_normalized.split())
            if not new_words or not existing_words:
                continue

            overlap = len(new_words & existing_words)
            if overlap == 0:
                continue

            # 5. Jaccard word overlap
            union = len(new_words | existing_words)
            jaccard = overlap / union if union > 0 else 0.0
            if jaccard >= threshold:
                return True

            # 6. Containment overlap (if either topic's core words are largely a subset of the other)
            min_words_count = min(len(new_words), len(existing_words))
            containment = overlap / min_words_count if min_words_count > 0 else 0.0
            if min_words_count >= 3 and containment >= 0.55:
                return True

            # 7. Fuzzy character ratio via SequenceMatcher
            seq_ratio = difflib.SequenceMatcher(None, new_normalized, existing_normalized).ratio()
            if seq_ratio >= 0.65:
                return True

        return False

    def get_history(self) -> List[str]:
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("topics", [])
        except Exception:
            return []

    def record_topic(self, topic: str, video_id: Optional[str] = None):
        """Immediately locks and records the topic in persistent history with zero duplicates."""
        clean_topic = topic.strip()
        self.session_used_topics.add(clean_topic.lower())
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            existing = data.setdefault("topics", [])
            # Only add to topics array if not already present or similar
            is_present = any(clean_topic.lower() == e.strip().lower() for e in existing)
            if not is_present and not self._is_topic_similar(clean_topic, existing, threshold=0.65):
                existing.append(clean_topic)

            if video_id:
                data.setdefault("video_ids", [])
                if video_id not in data["video_ids"]:
                    data["video_ids"].append(video_id)

            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print_warning(f"Could not update published history: {e}")

    def get_trending_topics(
        self, count: int = 5, niche: str = "space", language: str = "en"
    ) -> List[str]:
        """Generate unique, non-repeating viral topics using Gemini with multi-factor deduplication and large fallback pools."""
        history = self.get_history() + list(self.session_used_topics)
        canon_niche, niche_focus = self.resolve_niche(niche, language=language)
        is_hindi = language.lower() in ("hi", "hindi")

        client = None
        if self.cfg.gemini_api_key:
            try:
                client = genai.Client(api_key=self.cfg.gemini_api_key)
            except Exception:
                pass

        if client:
            # Provide up to 150 historical topics as strict negative constraints
            past_topics_str = ", ".join(f"'{t}'" for t in history[-150:]) if history else "None"
            entropy_seed = int(time.time() * 1000) % 999999
            lang_directive = (
                "in 100% authentic pure Devanagari Hindi (शुद्ध देवनागरी हिंदी केवल, absolutely NO English or Romanized Hinglish words)"
                if is_hindi
                else "in punchy, curiosity-inducing English"
            )

            # Request 3x candidate topics so our deduplication filter can discard any that resemble history
            req_count = max(count * 3, 6)

            prompt = f"""You are a viral YouTube Shorts growth strategist and documentary researcher.
Generate {req_count} completely fresh, mind-bending, high-CTR video topics in the niche: '{niche_focus}' {lang_directive}.

STRICT NEGATIVE CONSTRAINT (ZERO REPETITION MANDATE):
The following {len(history[-150:])} topics have ALREADY been covered and MUST NEVER be repeated, closely rephrased, or recycled:
[{past_topics_str}]

Requirements:
1. Each topic must evoke intense curiosity, awe, or a shocking revelation.
2. Formatted as punchy questions or jaw-dropping statements.
3. Every idea MUST explore a completely DIFFERENT subject, historical anomaly, or scientific mystery.
4. DO NOT reuse any core subject from the history list above.
5. Randomization Seed: {entropy_seed}.

Return ONLY a valid JSON list of strings, for example:
{json.dumps(["तारे के पास समय उल्टा क्यों चलने लगता है?", "कप्पाडोसिया के नीचे खोजी गई 12000 साल पुरानी भूमिगत नगरी का सच"] if is_hindi else ["Why You Would Age Backwards Near a Neutron Star", "The 12000-Year-Old Underground City Discovered Beneath Cappadocia"])}
"""
            for model_name in CANDIDATE_MODELS:
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.92,
                        ),
                    )
                    candidates = json.loads(resp.text)
                    if isinstance(candidates, list) and len(candidates) >= 1:
                        # Filter candidate topics with multi-factor deduplication
                        valid_topics: List[str] = []
                        for cand in candidates:
                            cand_str = str(cand).strip()
                            if not cand_str:
                                continue
                            if not self._is_topic_similar(cand_str, history + valid_topics):
                                valid_topics.append(cand_str)
                                if len(valid_topics) >= count:
                                    break

                        if valid_topics:
                            valid_topics = _ensure_scripture_topic_identity(canon_niche, valid_topics)
                            for vt in valid_topics:
                                self.session_used_topics.add(vt.lower())
                                # Immediately record so subsequent slots in batch cannot collide
                                self.record_topic(vt)
                            return valid_topics
                except Exception as e:
                    print_warning(f"TrendFinder model attempt failed: {e}")
                    continue

        # Niche-specific fallback pool with diverse topics per niche
        if is_hindi:
            pool = NICHE_FALLBACKS_HI.get(canon_niche, NICHE_FALLBACKS_HI.get("ancient_engineering", []))
            if not pool:
                pool = NICHE_FALLBACKS_HI.get("mystery", [])
        else:
            pool = NICHE_FALLBACKS.get(canon_niche, NICHE_FALLBACKS.get("mystery", []))

        # Randomize order to prevent sequential repetition
        shuffled_pool = list(pool)
        random.shuffle(shuffled_pool)

        available = [t for t in shuffled_pool if not self._is_topic_similar(t, history)]
        if len(available) >= count:
            selected = available[:count]
        else:
            # If available pool is small, supplement with dynamic parameterized angles
            selected = available
            needed = count - len(selected)
            if is_hindi:
                dynamic_modifiers = [
                    "इतिहास और विज्ञान का अनसुलझा सच:",
                    "वैज्ञानिकों को हैरान कर देने वाला रहस्य:",
                    "प्राचीन काल की अद्भुत गुप्त तकनीक:",
                    "प्रकृति और ब्रह्मांड का यह चौंकाने वाला चमत्कार:",
                ]
            else:
                dynamic_modifiers = [
                    "The Untold Reality Behind",
                    "The Declassified Scientific Truth About",
                    "Why Physicists Are Baffled By",
                    "The Ancient Anomaly Found Inside",
                    "What Really Happened During The Mystery Of",
                ]
            for i in range(needed):
                mod = random.choice(dynamic_modifiers)
                base = pool[i % len(pool)]
                dynamic_topic = f"{mod} {base}"
                if not self._is_topic_similar(dynamic_topic, history + selected):
                    selected.append(dynamic_topic)
                else:
                    selected.append(f"{base} [Deep Dive Mystery]")

        selected = _ensure_scripture_topic_identity(canon_niche, selected)
        for s in selected:
            self.session_used_topics.add(s.lower())
            self.record_topic(s)

        return selected

    def get_single_topic(self, niche: str, language: str = "en") -> str:
        """Get 1 fresh non-repeating viral topic for the given niche and immediately lock it."""
        topics = self.get_trending_topics(count=1, niche=niche, language=language)
        if topics:
            selected = topics[0]
            self.session_used_topics.add(selected.lower())
            self.record_topic(selected)
            return selected

        is_hindi = str(language).lower().startswith("hi")
        fallback = "ब्रह्मांड का सबसे रहस्यमयी अनसुलझा सच" if is_hindi else "The Most Mind-Blowing Unsolved Mystery In The Universe"
        self.session_used_topics.add(fallback.lower())
        self.record_topic(fallback)
        return fallback
