"""Master Paired Dual-Track Alien Interview Generator.

Generates identical 10-scene visual cuts and identical BGM for both
English and Hindi editions of each Alien Interview episode.
Only the spoken dialogue (US English vs Hindi) and ASS subtitles change!
"""

import os
import json
import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from autotube.config import get_config, PROJECT_ROOT
from autotube.scripting.alien_tracker import AlienSeriesTracker, ALIEN_SERIES_CHAPTERS
from autotube.scripting.models import ShortScript, ShortScene
from autotube.voice.tts_engine import TTSEngine, compute_scene_durations
from autotube.media.visual_waterfall import acquire_scene_visuals_waterfall
from autotube.media.background_music import BackgroundMusicManager
from autotube.media.cloud_video_gen import CloudVideoGenerator
from autotube.media.pexels_video import PexelsVideoFetcher, get_pexels_keywords_for_scene
from autotube.video.shorts_builder import ShortsBuilder
from autotube.uploader.youtube_upload import YouTubeUploader
from autotube.scheduler.autopilot import get_timezone
from autotube.utils.file_utils import sanitize_filename
from autotube.utils.console import (
    print_banner,
    print_error,
    print_info,
    print_panel,
    print_step,
    print_success,
    print_warning,
)

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


class PairedScene(BaseModel):
    scene_number: int
    speaker: str = Field(description="'nurse' (Matilda) or 'alien' (Airl)")
    visual_subject: str = Field(description="Visual search query in English")
    visual_description: str = Field(description="Cinematic 1947 photographic prompt in English")
    narration_en: str = Field(description="Spoken dialogue in English (15-20 words)")
    narration_hi: str = Field(description="Spoken dialogue in natural Hindi (15-20 words)")


class PairedAlienScript(BaseModel):
    part: int
    title_en: str
    title_hi: str
    evidence_proof: str
    key_quote: str
    scenes: List[PairedScene]
    pinned_comment_en: str
    pinned_comment_hi: str
    tags: List[str]


class PairedAlienGenerator:
    """Orchestrates 100% synchronized dual-language video generation."""

    def __init__(self, api_key: Optional[str] = None):
        self.cfg = get_config()
        self.api_key = api_key or self.cfg.gemini_api_key or os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=self.api_key) if (genai and self.api_key) else None
        self.tracker = AlienSeriesTracker()

    def generate_bilingual_script(self, part: int) -> PairedAlienScript:
        """Generate a single unified master script with 1-to-1 matching English and Hindi dialogue."""
        part_num = part
        chapter = self.tracker.get_current_chapter(part_override=part)
        if part == 1:
            print_info(f"Using Canonical Book Transcript for Part 1: {chapter['title_en']}")
            return self._generate_fallback_paired_script(chapter)

        print_info(f"Writing Bilingual Master Script for Part {part_num}: {chapter['title_en']}")

        prompt = f"""You are creating the official bilingual 1947 Roswell interrogation tape script for Part {part_num} of the 'Alien Interview' series (based on transcripts between US Army Nurse Matilda MacElroy and Roswell alien 'Airl' from The Domain).

EPISODE METADATA:
Part Number: {part_num}
English Topic: {chapter['title_en']}
Hindi Topic: {chapter['title_hi']}
Book Chapter: {chapter['book_chapter']}
Core Theme: {chapter['core_theme']}
Documented Proof / Evidence: {chapter['evidence_proof']}
Airl's Core Quote: "{chapter['key_quote']}"

CRITICAL SCRIPTING RULES:
1. DUAL SPEAKERS (REAL INTERVIEW):
   - Alternating interrogation dialogue between 'nurse' (Matilda MacElroy) and 'alien' (Airl).
   - Nurse asks intense investigative questions into her vintage microphone.
   - Alien Airl responds with calm, cosmic, telepathic revelations into Matilda's mind.
2. 1-TO-1 MATCHING SCENES:
   - Provide exactly 9 to 11 scenes in 'scenes'.
   - Each scene MUST have IDENTICAL visual_subject and visual_description in English (so the same video clips work for both language cuts).
   - Each scene MUST have 'narration_en' (spoken English dialogue) and 'narration_hi' (exact matching spoken Hindi dialogue).
   - Word count per language across all scenes MUST be 165 to 195 words (~65 to 75 seconds runtime).
3. SEAMLESS INFINITE LOOP (110%+ Retention Hack):
   - The very last sentence spoken in Scene 10 or 11 MUST seamlessly connect and flow grammatically right back into the opening sentence of Scene 1 with zero awkward pause!
4. HIGH-CTR TITLES:
   - title_en: Extreme curiosity hook (e.g., "NURSE ASKED: 'What Happens After Death?' The Alien's Answer Shocked The Pentagon ⚠️ Part {part_num} #Shorts")
   - title_hi: High-drama Hindi hook (e.g., "NURSE ने पूछा: 'मौत के बाद आत्मा कहाँ जाती है?' Alien का जवाब सुनकर रोंगटे खड़े हो गए! Part {part_num} #Shorts")
5. CONTROVERSY POLL PINNED COMMENTS:
   - pinned_comment_en: Existential question compelling viewers to comment YES or NO.
   - pinned_comment_hi: Matching Hindi debate question.
6. NEXT PART CLIFFHANGER:
   - Final scene must tease the secret of Part {part_num + 1} and demand viewers subscribe.

Return valid JSON matching the PairedAlienScript schema.
"""

        models_to_try = [
            "gemini-3.1-flash-lite-preview",
            "gemini-3.8-flash",
            "gemini-flash-latest",
            "gemini-3-flash-preview",
        ]

        if self.client:
            for model_name in models_to_try:
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=PairedAlienScript,
                            temperature=0.7,
                        ),
                    )
                    parsed = PairedAlienScript.model_validate_json(response.text)
                    print_success(f"Master Bilingual Script generated with {model_name} ({len(parsed.scenes)} scenes)!")
                    return parsed
                except Exception as e:
                    print_warning(f"Model {model_name} failed: {e}. Trying fallback model...")

        # Smart fallback if API unavailable
        return self._generate_fallback_paired_script(chapter)

    def acquire_alien_scene_visuals(self, scenes: List[Any]) -> List[Path]:
        """Acquire video clips for each scene.
        Priority:
        1. For non-character scenes (documents, space, military, crash): Real Pexels HD stock videos!
        2. For character dialogue scenes (Airl, Nurse): Canonical character motion clips (.mp4)
        3. Fallback to Pexels search for any failed asset
        4. Final fallback to canonical images
        """
        assets_dir = PROJECT_ROOT / "assets" / "alien_interview"
        videos_dir = assets_dir / "videos"
        assets_dir.mkdir(parents=True, exist_ok=True)
        videos_dir.mkdir(parents=True, exist_ok=True)

        pexels = PexelsVideoFetcher()
        if pexels.is_configured():
            print_info("🎬 Pexels Stock Video Engine active — fetching real video footage!")

        visual_cuts: List[Path] = []
        for idx, s in enumerate(scenes):
            speaker = getattr(s, "speaker", "").lower()
            subject = getattr(s, "visual_subject", "").lower()

            video_clip: Optional[Path] = None

            # Strategy A: For narrator / atmospheric scenes, prefer REAL PEXELS STOCK VIDEO
            if speaker in ("narrator", "") or any(w in subject for w in ("crash", "space", "document", "general", "military", "galaxy", "fleet")):
                if pexels.is_configured():
                    query = get_pexels_keywords_for_scene(speaker, subject, scene_index=idx)
                    video_clip = pexels.get_scene_video(search_query=query, scene_index=idx)

            # Strategy B: For character scenes or if Pexels returned nothing, use canonical motion clips
            if not video_clip:
                if speaker == "alien":
                    if any(w in subject for w in ("eye", "macro", "stare", "cliffhanger")):
                        asset_key = "airl_eyes_macro"
                    elif any(w in subject for w in ("domain", "fleet", "space")):
                        asset_key = "domain_fleet_vision"
                    else:
                        asset_key = "airl_speaking" if (idx % 2 != 0) else "airl_portrait"
                elif speaker == "nurse":
                    asset_key = "nurse_matilda" if (idx % 2 == 0) else "interrogation_twoshot"
                else:
                    if any(w in subject for w in ("document", "evidence", "memo", "paper")):
                        asset_key = "roswell_documents"
                    elif any(w in subject for w in ("general", "officer", "military")):
                        asset_key = "generals_observing"
                    else:
                        asset_key = "interrogation_twoshot"

                # Check pre-rendered motion video
                motion_video = videos_dir / f"{asset_key}_motion.mp4"
                source_image = assets_dir / f"{asset_key}.jpg"

                if motion_video.exists() and motion_video.stat().st_size > 50000:
                    video_clip = motion_video
                    print_info(f"   [Scene {idx+1}] Using canonical motion clip: {motion_video.name}")
                elif source_image.exists():
                    video_clip = source_image
                    print_info(f"   [Scene {idx+1}] Using canonical image: {source_image.name}")

            # Strategy C: Ultimate Pexels fallback
            if not video_clip and pexels.is_configured():
                fallback_query = get_pexels_keywords_for_scene(speaker, subject, scene_index=idx)
                video_clip = pexels.get_scene_video(search_query=fallback_query, scene_index=idx)

            # Strategy D: Default image fallback
            if not video_clip:
                video_clip = assets_dir / "airl_portrait.jpg"

            visual_cuts.append(video_clip)

        return visual_cuts

    def _generate_fallback_paired_script(self, chapter: Dict[str, Any]) -> PairedAlienScript:
        """Deterministic canonical script faithful to Lawrence R. Spencer's Alien Interview book.
        Features a powerful opening narrator hook to grip the audience and establish Roswell context.
        """
        p = chapter["part_number"]
        scenes = [
            # SCENE 1: POWERFUL OPENING NARRATOR HOOK (Grips the viewer, gives instant context!)
            PairedScene(
                scene_number=1,
                speaker="narrator",
                visual_subject="roswell crash desert night ufo",
                visual_description="Cinematic desert crash site at night, smoking wreckage under spotlight, soldiers surrounding, vintage 1947 style, 8k vertical",
                narration_en="July 1947. Roswell, New Mexico. A UFO crashed in the desert. The US military captured one alien alive. For 78 years, this interview was classified TOP SECRET. This is the official transcript.",
                narration_hi="जुलाई 1947. रोसवेल, न्यू मेक्सिको। एक यूएफओ क्रैश हुआ और सेना ने एक एलियन को ज़िंदा पकड़ा। 78 सालों तक यह इंटरव्यू टॉप सीक्रेट रहा। यह है उस गुप्त बातचीत का पहला भाग।",
            ),
            # SCENE 2: NURSE INTRODUCES HERSELF
            PairedScene(
                scene_number=2,
                speaker="nurse",
                visual_subject="vintage nurse 1940s microphone retro",
                visual_description="USAAF Flight Nurse Matilda MacElroy at wooden interrogation desk with vintage steel microphone, 8k vertical",
                narration_en="My name is Nurse Matilda MacElroy. Out of everyone on the base, the entity would only communicate with me. They sat me across from it in Building 84.",
                narration_hi="मेरा नाम नर्स मटिल्डा मैकलरॉय है। पूरे बेस में वह एलियन सिर्फ मुझसे बात कर रही थी। मुझे उसके सामने एक लोहे की मेज पर बैठाया गया।",
            ),
            # SCENE 3: CLASSIFIED DOCUMENTS & COVER-UP
            PairedScene(
                scene_number=3,
                speaker="narrator",
                visual_subject="classified documents typewriter secret memo",
                visual_description="July 8 1947 RAAF flying saucer press release and official FBI memo stamped TOP SECRET, 8k vertical",
                narration_en="Colonel Blanchard announced to the world: 'RAAF Captures Flying Saucer'. Hours later, General Ramey ordered a complete cover-up, claiming it was just a weather balloon.",
                narration_hi="कर्नल ब्लैंचर्ड ने प्रेस को बताया: 'उड़न तश्तरी बरामद हुई'। लेकिन कुछ ही घंटों में सेना ने इसे मौसम का गुब्बारा बताकर सच को दबा दिया।",
            ),
            # SCENE 4: FIRST QUESTION TO AIRL
            PairedScene(
                scene_number=4,
                speaker="nurse",
                visual_subject="interrogation room dark spotlight two shot",
                visual_description="Wide two-shot inside Building 84 interrogation room with Matilda sitting across from Alien Airl under hanging lamp, 8k vertical",
                narration_en="I leaned toward the microphone and asked: 'Can you speak? What is your name?'",
                narration_hi="मैंने कांपते हाथों से माइक पकड़ा और पूछा: 'क्या तुम बोल सकती हो? तुम्हारा नाम क्या है?'",
            ),
            # SCENE 5: AIRL'S TELEPATHIC VOICE REVEALED
            PairedScene(
                scene_number=5,
                speaker="alien",
                visual_subject="alien dark room sci-fi telepathic eyes",
                visual_description="Close up of grey extraterrestrial Airl with huge glossy black almond eyes staring forward, 8k vertical",
                narration_en="No sound came from its lips. Instead, a calm telepathic thought entered my mind: 'I do not speak with vocal cords. I communicate mind to mind. I am Airl.'",
                narration_hi="कमरे में कोई आवाज़ नहीं हुई। सीधे मेरे दिमाग में एक विचार आया: 'मैं मुंह से नहीं बोलती। मैं सीधे मन से बात करती हूँ। मेरा नाम एयरल है।'",
            ),
            # SCENE 6: WHERE ARE YOU FROM?
            PairedScene(
                scene_number=6,
                speaker="nurse",
                visual_subject="nurse speaking microphone retro vintage",
                visual_description="Nurse Matilda holding debriefing clipboard writing stenographer notes with vintage pen, 8k vertical",
                narration_en="My heart was pounding. I asked: 'Where do you come from, Airl? And why did you enter our airspace?'",
                narration_hi="मेरी धड़कनें तेज़ हो गईं। मैंने पूछा: 'एयरल, तुम कहाँ से आई हो? और हमारे इलाके में क्यों आई?'",
            ),
            # SCENE 7: THE DOMAIN FLEET REVELATION
            PairedScene(
                scene_number=7,
                speaker="alien",
                visual_subject="galaxy stars nebula space spaceship",
                visual_description="Cosmic projection of disc starships of The Domain Expeditionary Force in deep space, 8k vertical",
                narration_en="Airl projected a vision of deep space into my mind: 'I am a pilot of The Domain Expeditionary Force. We came to investigate your nuclear tests at White Sands.'",
                narration_hi="एयरल ने मेरे दिमाग में अंतरिक्ष का दृश्य दिखाया: 'मैं द डोमेन सेना की पायलट हूँ। हम वाइट सैंड्स में हुए परमाणु परीक्षणों की जांच करने आए थे।'",
            ),
            # SCENE 8: MILITARY IN PANIC
            PairedScene(
                scene_number=8,
                speaker="narrator",
                visual_subject="military generals meeting war room retro",
                visual_description="General Roger Ramey and counter-intelligence officers watching through one-way glass with audio tape recorder, 8k vertical",
                narration_en="Behind the one-way glass, General Ramey and intelligence officers panicked. But Airl's next revelation shook them to the core.",
                narration_hi="एकतरफा शीशे के पीछे जनरल और खुफिया अधिकारी घबरा गए। लेकिन एयरल का अगला खुलासा सबसे भयानक था।",
            ),
            # SCENE 9: THE DOLL BODY TRUTH
            PairedScene(
                scene_number=9,
                speaker="alien",
                visual_subject="mysterious alien eyes dark cosmic",
                visual_description="Alien Airl leaning forward in chair with cosmic gaze, 8k vertical",
                narration_en="Airl looked at me: 'This body is not who I am. It is a synthetic doll body. I am an immortal spiritual being. And so are you.'",
                narration_hi="एयरल ने मेरी आंखों में देखा: 'यह शरीर मेरा असली रूप नहीं है। यह सिर्फ एक पुतला है। मैं एक अमर आत्मा हूँ—और तुम भी वही हो।'",
            ),
            # SCENE 10: CLIFFHANGER & CTA
            PairedScene(
                scene_number=10,
                speaker="narrator",
                visual_subject="suspense dark mystery shadows cliffhanger",
                visual_description="Extreme macro close up of Airl's cosmic eyes reflecting starry void, 8k vertical",
                narration_en="In Part 2: Airl reveals why Earth is secretly an amnesia prison planet, and where your soul goes after death. Subscribe now so you don't miss Part 2.",
                narration_hi="पार्ट 2 में: एयरल बताएगी कि पृथ्वी एक अंतरिक्ष जेल क्यों है, और मौत के बाद आत्मा का क्या होता है। सब्सक्राइब करें ताकि पार्ट 2 छूट न जाए।",
            ),
        ]

        return PairedAlienScript(
            part=p,
            title_en="78 Years Secret: Roswell Alien's First Words Shocked the US Military 😱 (Part 1) #Shorts",
            title_hi="78 साल का राज: रोसवेल एलियन के पहले शब्दों ने सेना को हिला दिया 😱 (Part 1) #Shorts",
            evidence_proof="July 8, 1947 RAAF Official Press Release issued by Col. William Blanchard & FBI Memo to J. Edgar Hoover",
            key_quote="I do not speak with vocal cords. I communicate mind to mind. I am Airl.",
            scenes=scenes,
            pinned_comment_en="Airl revealed that her body is just a shell and humans are immortal spiritual beings. Do you believe in past lives? Comment YES or NO below 👇",
            pinned_comment_hi="एयरल ने कहा कि उसका शरीर सिर्फ एक पुतला है और हम सब अमर आत्माएं हैं। क्या आपको लगता है आत्मा अमर है? कमेंट में 'हाँ' या 'ना' लिखें! 👇",
            tags=["#Shorts", "#AlienInterview", "#Roswell1947", "#Airl", "#MatildaMacElroy", "#TheDomain", "#SciFiDocumentary"],
        )

    def generate_and_render_paired_episode(
        self,
        part: int,
        upload: bool = True,
        privacy_en: str = "private",
        privacy_hi: str = "public",
        schedule: bool = True,
        single_lang: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build both English and Hindi versions with IDENTICAL VISUALS & BGM."""
        total_steps = 6
        temp_dir = self.cfg.paths.temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)
        shorts_dir = self.cfg.paths.output_dir / "shorts"
        shorts_dir.mkdir(parents=True, exist_ok=True)

        do_en = single_lang is None or single_lang.lower() in ("en", "english", "both", "all")
        do_hi = single_lang is None or single_lang.lower() in ("hi", "hindi", "both", "all")

        # -------------------------------------------------------------
        # STEP 1: Generate Master Bilingual Script
        # -------------------------------------------------------------
        print_step(1, total_steps, f"Writing Master Bilingual Script (Part {part})")
        paired_script = self.generate_bilingual_script(part=part)

        # Convert to separate ShortScript objects for downstream compatibility
        script_en_scenes = [
            ShortScene(
                scene_number=s.scene_number,
                visual_subject=s.visual_subject,
                visual_description=s.visual_description,
                narration=s.narration_en,
                speaker=s.speaker,
            )
            for s in paired_script.scenes
        ]
        script_hi_scenes = [
            ShortScene(
                scene_number=s.scene_number,
                visual_subject=s.visual_subject,
                visual_description=s.visual_description,
                narration=s.narration_hi,
                speaker=s.speaker,
            )
            for s in paired_script.scenes
        ]

        script_en = ShortScript(
            topic=paired_script.title_en,
            title=paired_script.title_en,
            hook=paired_script.scenes[0].narration_en if paired_script.scenes else paired_script.title_en,
            narration=" ".join(s.narration_en for s in paired_script.scenes),
            scenes=script_en_scenes,
            pinned_comment=paired_script.pinned_comment_en,
            tags=paired_script.tags,
        )
        script_hi = ShortScript(
            topic=paired_script.title_hi,
            title=paired_script.title_hi,
            hook=paired_script.scenes[0].narration_hi if paired_script.scenes else paired_script.title_hi,
            narration=" ".join(s.narration_hi for s in paired_script.scenes),
            scenes=script_hi_scenes,
            pinned_comment=paired_script.pinned_comment_hi,
            tags=paired_script.tags,
        )

        slug_base = f"alien_interview_part_{part}"

        # -------------------------------------------------------------
        # STEP 2: Acquire Synchronized Canonical Character Cuts ONCE (Shared by EN & HI)
        # -------------------------------------------------------------
        print_step(2, total_steps, f"Acquiring Canonical Alien Interview Visual Cuts (SHARED for English & Hindi)")
        shared_visual_assets = self.acquire_alien_scene_visuals(paired_script.scenes)
        print_success(f"🎬 Locked {len(shared_visual_assets)} canonical character cuts (Alien Airl + Nurse Matilda)!")

        # -------------------------------------------------------------
        # STEP 3: Select Atmospheric BGM ONCE (Shared by EN & HI)
        # -------------------------------------------------------------
        print_step(3, total_steps, "Selecting Atmospheric BGM (SHARED for English & Hindi)")
        bgm_mgr = BackgroundMusicManager()
        shared_bgm_track = bgm_mgr.get_music_for_subject(niche="alien", topic="roswell")
        print_success(f"🎵 Master BGM locked: {shared_bgm_track.name if shared_bgm_track else 'Default'}")

        builder = ShortsBuilder()
        final_en_path = None
        final_hi_path = None

        # -------------------------------------------------------------
        # STEP 4: Render Track 1 - ENGLISH VIDEO
        # -------------------------------------------------------------
        if do_en:
            print_step(4, total_steps, "Synthesizing & Rendering ENGLISH Edition (Nurse Rachel + Alien Daniel)")
            tts_en = TTSEngine(default_voice="rachel")
            audio_en_path = temp_dir / f"{slug_base}_en_voice.mp3"
            tts_en_res = tts_en.synthesize_dialogue(
                scenes=script_en.scenes,
                output_audio_path=audio_en_path,
                language="en",
            )
            scene_durations_en = tts_en_res.scene_durations or compute_scene_durations(
                scenes=script_en.scenes,
                words=tts_en_res.words,
                total_duration=tts_en_res.duration_seconds,
            )

            out_en_path = shorts_dir / f"{slug_base}_en.mp4"
            final_en_path = builder.build_short(
                audio_path=tts_en_res.audio_path,
                output_path=out_en_path,
                scene_assets=shared_visual_assets,
                scene_durations=scene_durations_en,
                subtitles_file=tts_en_res.subtitles_ass_path,
                music_path=shared_bgm_track,
            )
            print_success(f"🎬 English Short successfully rendered: {final_en_path.resolve() if final_en_path else 'None'}")
        else:
            print_step(4, total_steps, "Skipping English Edition (Single-language mode: Hindi only)")

        # -------------------------------------------------------------
        # STEP 5: Render Track 2 - HINDI VIDEO (SAME VISUALS & BGM)
        # -------------------------------------------------------------
        if do_hi:
            print_step(5, total_steps, "Synthesizing & Rendering HINDI Edition (Nurse Swara + Alien Madhur)")
            tts_hi = TTSEngine(default_voice="swara")
            audio_hi_path = temp_dir / f"{slug_base}_hi_voice.mp3"
            tts_hi_res = tts_hi.synthesize_dialogue(
                scenes=script_hi.scenes,
                output_audio_path=audio_hi_path,
                language="hi",
            )
            scene_durations_hi = tts_hi_res.scene_durations or compute_scene_durations(
                scenes=script_hi.scenes,
                words=tts_hi_res.words,
                total_duration=tts_hi_res.duration_seconds,
            )

            out_hi_path = shorts_dir / f"{slug_base}_hi.mp4"
            final_hi_path = builder.build_short(
                audio_path=tts_hi_res.audio_path,
                output_path=out_hi_path,
                scene_assets=shared_visual_assets,  # EXACT SAME VISUAL ASSETS!
                scene_durations=scene_durations_hi,
                subtitles_file=tts_hi_res.subtitles_ass_path,
                music_path=shared_bgm_track,        # EXACT SAME BGM TRACK!
            )
            print_success(f"🎬 Hindi Short successfully rendered: {final_hi_path.resolve() if final_hi_path else 'None'}")
        else:
            print_step(5, total_steps, "Skipping Hindi Edition (Single-language mode: English only)")

        # -------------------------------------------------------------
        # STEP 6: YouTube Upload & Scheduling
        # -------------------------------------------------------------
        results = {
            "part": part,
            "en_path": str(final_en_path) if final_en_path else None,
            "hi_path": str(final_hi_path) if final_hi_path else None,
            "en_url": None,
            "hi_url": None,
        }

        uploader = YouTubeUploader() if upload else None

        if do_en and final_en_path and final_en_path.exists():
            if upload and uploader:
                sched_time_en = None
                if schedule and privacy_en == "private":
                    slot_tz = get_timezone("us")
                    now = datetime.datetime.now(datetime.timezone.utc)
                    local_now = datetime.datetime.now(slot_tz)
                    sched_dt = datetime.datetime(
                        local_now.year, local_now.month, local_now.day, 18, 30, 0, tzinfo=slot_tz
                    )
                    if sched_dt.astimezone(datetime.timezone.utc) <= now:
                        sched_dt += datetime.timedelta(days=1)
                    sched_time_en = sched_dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                print_info(f"Uploading English Edition (Scheduled: {sched_time_en or 'Direct Public'})...")
                url_en = uploader.upload_video(
                    video_path=final_en_path,
                    title=f"{paired_script.title_en}",
                    description=(
                        f"{script_en.narration}\n\n"
                        f"Evidence / Proof Cited: {paired_script.evidence_proof}\n"
                        f"Based on 'Alien Interview' transcripts by Lawrence R. Spencer\n\n"
                        f"{' '.join(paired_script.tags)}"
                    ),
                    tags=paired_script.tags + ["alien interview", "roswell 1947", "airl", "the domain"],
                    privacy_status=privacy_en,
                    publish_at=sched_time_en,
                    pinned_comment=paired_script.pinned_comment_en,
                )
                results["en_url"] = url_en
                if url_en:
                    vid_id_en = url_en.split("/")[-1].split("=")[-1]
                    self.tracker.mark_part_completed(part=part, lang="en", video_id=vid_id_en)
                else:
                    self.tracker.mark_part_completed(part=part, lang="en", video_id="rendered_local")
            else:
                self.tracker.mark_part_completed(part=part, lang="en", video_id="rendered_local")

        if do_hi and final_hi_path and final_hi_path.exists():
            if upload and uploader:
                print_info(f"Uploading Hindi Edition ({privacy_hi})...")
                url_hi = uploader.upload_video(
                    video_path=final_hi_path,
                    title=f"{paired_script.title_hi}",
                    description=(
                        f"{script_hi.narration}\n\n"
                        f"साक्ष्य / दस्तावेज़: {paired_script.evidence_proof}\n"
                        f"Based on 'Alien Interview' transcripts by Lawrence R. Spencer\n\n"
                        f"{' '.join(paired_script.tags)}"
                    ),
                    tags=paired_script.tags + ["alien interview hindi", "roswell 1947", "airl in hindi"],
                    privacy_status=privacy_hi,
                    pinned_comment=paired_script.pinned_comment_hi,
                )
                results["hi_url"] = url_hi
                if url_hi:
                    vid_id_hi = url_hi.split("/")[-1].split("=")[-1]
                    self.tracker.mark_part_completed(part=part, lang="hi", video_id=vid_id_hi)
                else:
                    self.tracker.mark_part_completed(part=part, lang="hi", video_id="rendered_local")
            else:
                self.tracker.mark_part_completed(part=part, lang="hi", video_id="rendered_local")

        print_success(f"🎯 Paired Part {part} Generation Complete! EN: {results['en_url'] or results['en_path']}, HI: {results['hi_url'] or results['hi_path']}")
        return results
