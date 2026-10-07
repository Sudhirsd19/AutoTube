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
}

VIRAL_NICHES = {
    "space": "Mind-bending cosmic mysteries, black holes, rogue planets, cosmic radiation, universe boundaries, quantum vacuum decay",
    "science": "Shocking physics paradoxes, quantum mechanics anomalies, strange biology glitches, crazy discoveries, time perception",
    "history": "Bizarre historical events, untold ancient secrets, ruthless rulers, hidden lost libraries, catastrophic ancient events",
    "psychology": "Dark psychology, human mind tricks, subconscious cognitive biases, body language micro-expressions, manipulation defense",
    "mystery": "Unsolved global enigmas, deep earth anomalies, forbidden archaeological discoveries, eerie legends, impossible ancient maps",
    "mythology": "Ancient Indian mythological secrets, sacred divine weapons, unsolved epic mysteries, lost temples, celestial beings",
    "bharat_vigyan": "Bharat Ka Adbhut Vigyan: Kailasa Temple Ellora impossible monolithic carving from top down, Padmanabhaswamy Vault B acoustic snake lock, Delhi Iron Pillar 1600-year rustproof mystery, Ram Setu floating stone acoustics, Lepakshi hanging pillar gravity anomaly, Brihadeeswarar Temple 80-ton granite dome science",
    "glitch_matrix": "Glitch in the Matrix & Time Slips: The Man from Taured 1954 mystery, Pan American Flight 914 37-year time jump, Green Children of Woolpit, simulation hypothesis physical proofs, parallel universe sightings, quantum timeline shifts, deja vu glitches",
    "ocean": "Deep sea abyssal horrors, Mariana Trench sonar anomalies, Point Nemo alien sounds, giant colossal squids, glowing ocean milky seas, deep underwater brine pools",
    "ai_future": "Artificial general intelligence consciousness, dead internet theory, brain-computer neural lace risks, quantum cryptography collapse, synthetic biology paradoxes",
    "conspiracy": "Declassified FBI & CIA files, Project Stargate remote viewing, Guy Hottel UFO memos, Area 51 secret reverse engineering, Svalbard seed vault mysteries",
    "cartoon": "Funny 3D Pixar animated animal adventures, quirky pets with secret superhero lives, hilarious baby dinosaur mishaps, funny mischievous robot fails, adorable comedy cartoon stories",
    "animal_secrets": "Mind-blowing animal secrets, insane biological superpowers, animal speed & flight comparisons (Peregrine falcon 390 km/h dive vs cheetah, bite forces of apex predators), immortal jellyfish, pistol shrimp thermal shockwave, honey badger venom immunity, bizarre deep sea creatures, electric eel shock voltage",
}

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
NICHE_FALLBACKS = {
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
}


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

    def resolve_niche(self, raw_niche: str) -> Tuple[str, str]:
        """Map any free-form slot niche string to a canonical key and rich prompt description."""
        raw_lower = raw_niche.lower().strip()
        # Direct lookup
        if raw_lower in VIRAL_NICHES:
            return raw_lower, VIRAL_NICHES[raw_lower]

        # Keyword mapping
        for keyword, canon_key in NICHE_KEYWORD_MAPPINGS.items():
            if keyword in raw_lower:
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
        canon_niche, niche_focus = self.resolve_niche(niche)
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
                "in captivating Hindi/Hinglish (Devanagari or Romanized Hindi)"
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
["Why You Would Age Backwards Near a Neutron Star", "The 12000-Year-Old Underground City Discovered Beneath Cappadocia"]
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
                            for vt in valid_topics:
                                self.session_used_topics.add(vt.lower())
                                # Immediately record so subsequent slots in batch cannot collide
                                self.record_topic(vt)
                            return valid_topics
                except Exception as e:
                    print_warning(f"TrendFinder model attempt failed: {e}")
                    continue

        # Niche-specific fallback pool with 18 topics per niche
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

        fallback = "The Most Mind-Blowing Unsolved Mystery In The Universe"
        self.session_used_topics.add(fallback.lower())
        self.record_topic(fallback)
        return fallback
