"""Full-Length 16:9 Widescreen Alien Interview Documentary Producer.

Features:
- Authentic character dialogue: First-person lines for Nurse Matilda, Alien Airl, and Narrator.
- 100% Speech-to-Scene Visual Alignment matching every spoken word.
- Rahasyamayi atmospheric ambient score (The Complex / Alien Mystery).
- Animated Subscribe + Like + Bell pop-up visual banner with crisp Bell Ding sound effect.
- 1920x1080 30fps widescreen video with burned subtitles and custom 16:9 thumbnail.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from PIL import Image, ImageFilter, ImageEnhance
from pydantic import BaseModel

from autotube.config import get_config, PROJECT_ROOT
from autotube.media.background_music import BackgroundMusicManager
from autotube.media.stock_fetcher import StockFetcher
from autotube.video.longform_builder import LongformBuilder
from autotube.video.thumbnail import ThumbnailGenerator
from autotube.voice.tts_engine import TTSEngine
from autotube.utils.ffmpeg_helper import get_media_duration, run_ffmpeg
from autotube.utils.console import (
    print_banner,
    print_error,
    print_info,
    print_panel,
    print_step,
    print_success,
    print_warning,
)


class AlienDocScene(BaseModel):
    scene_number: int
    speaker: str  # 'narrator', 'nurse', or 'alien'
    visual_key: str
    narration_en: str
    narration_hi: str


CANONICAL_FULL_DOC_SCENES: List[AlienDocScene] = [
    # Scene 1: The 1947 Crash [NARRATOR]
    AlienDocScene(
        scene_number=1,
        speaker="narrator",
        visual_key="crash",
        narration_en="In July 1947, an extraterrestrial craft crashed into the New Mexico desert. What the US Army recovered was classified Top Secret. Out of everyone on the military base, the surviving extraterrestrial refused to speak with generals—it would only communicate with one young flight nurse.",
        narration_hi="जुलाई 1947 में, न्यू मैक्सिको के रेगिस्तान में एक उड़न तश्तरी दुर्घटनाग्रस्त हुई। मलबे से बरामद जीवित एलियन ने किसी जनरल या वैज्ञानिक से बात करने से इनकार कर दिया—वह केवल एक युवा नर्स से संवाद करने को तैयार थी।",
    ),
    # Scene 2: Nurse Matilda MacElroy [NURSE]
    AlienDocScene(
        scene_number=2,
        speaker="nurse",
        visual_key="nurse",
        narration_en="My name is Nurse Matilda MacElroy. They escorted me into Building 84 and sat me across from the entity. I leaned toward my vintage microphone and asked: 'Can you hear me? What is your name, and where do you come from?'",
        narration_hi="मेरा नाम नर्स मटिल्डा मैकलरॉय है। मुझे बिल्डिंग 84 के गुप्त कमरे में ले जाया गया। मैंने कांपते हाथों से माइक पकड़ा और पूछा: 'क्या तुम मेरी आवाज़ सुन सकती हो? तुम्हारा नाम क्या है, और तुम कहाँ से आई हो?'",
    ),
    # Scene 3: Alien Airl First Words [ALIEN]
    AlienDocScene(
        scene_number=3,
        speaker="alien",
        visual_key="airl_eyes",
        narration_en="I do not communicate with physical vocal cords. I speak mind to mind directly into your consciousness. I am Airl. I am an officer, pilot, and engineer of The Domain Expeditionary Force.",
        narration_hi="मैं मुंह से या वोकल कॉर्ड से नहीं बोलती। मैं सीधे तुम्हारे मन और विचारों में बात करती हूँ। मेरा नाम एयरल है। मैं द डोमेन सेना की पायलट और इंजीनियर हूँ।",
    ),
    # Scene 4: The Domain Space Fleet [ALIEN]
    AlienDocScene(
        scene_number=4,
        speaker="alien",
        visual_key="domain_fleet",
        narration_en="The Domain controls millions of planetary systems across this galaxy. We entered your solar system to investigate atmospheric atomic explosions conducted by your military at the White Sands testing grounds.",
        narration_hi="द डोमेन इस आकाशगंगा के लाखों सौरमंडलों पर नियंत्रण रखता है। हम वाइट सैंड्स में आपकी सेना द्वारा किए गए परमाणु बम परीक्षणों की जांच करने आपके सौरमंडल में आए थे।",
    ),
    # Scene 5: Nurse Asks About The Doll Body [NURSE]
    AlienDocScene(
        scene_number=5,
        speaker="nurse",
        visual_key="synthetic_body",
        narration_en="I looked down at the medical autopsy reports in disbelief. I asked her: 'Our military surgeons say your body has no lungs, no stomach, no blood, and no internal organs. How are you alive? What is this body?'",
        narration_hi="मैंने अविश्वास से मेडिकल रिपोर्ट देखी और पूछा: 'हमारे डॉक्टरों का कहना है कि तुम्हारे शरीर में न फेफड़े हैं, न खून, और न ही कोई आंतरिक अंग। फिर तुम जीवित कैसे हो? तुम्हारा यह शरीर क्या है?'",
    ),
    # Scene 6: Airl Explains IS-BE Immortal Soul [ALIEN]
    AlienDocScene(
        scene_number=6,
        speaker="alien",
        visual_key="is_be_soul",
        narration_en="This body is not who I am. It is an engineered synthetic doll body—a biological android operated telepathically by my consciousness. I am not physical matter. I am an IS-BE: an immortal spiritual being. And so are you, Matilda.",
        narration_hi="यह शरीर मेरा असली रूप नहीं है। यह केवल एक सिंथेटिक पुतला है—एक जैविक रोबोट जिसे मैं अपने विचारों से नियंत्रित करती हूँ। मैं एक IS-BE हूँ: एक अमर आध्यात्मिक आत्मा। और मटिल्डा... तुम भी वही हो।",
    ),
    # Scene 7: Nurse Asks Why Humans Suffer & Forget [NURSE]
    AlienDocScene(
        scene_number=7,
        speaker="nurse",
        visual_key="twoshot",
        narration_en="A wave of emotion hit me. I asked: 'If humans are immortal spiritual beings, why do we suffer on this planet? Why does nobody remember who they were before being born on Earth?'",
        narration_hi="मेरे पूरे शरीर में सिहरन दौड़ गई। मैंने पूछा: 'अगर इंसान अमर आत्माएं हैं, तो हम इतना दुख क्यों झेलते हैं? किसी को यह याद क्यों नहीं रहता कि वे इस धरती पर जन्म लेने से पहले कौन थे?'",
    ),
    # Scene 8: Airl on Earth as Prison Planet [ALIEN]
    AlienDocScene(
        scene_number=8,
        speaker="alien",
        visual_key="prison_planet",
        narration_en="Because Earth is not an ordinary nursery of life. Earth is a cosmic prison planet. For billions of years, a galactic totalitarian empire known as the Old Empire has used Earth as a dumping ground for artists, philosophers, and political rebels.",
        narration_hi="क्योंकि पृथ्वी कोई सामान्य ग्रह नहीं है। पृथ्वी एक अंतरिक्ष जेल है। लाखों सालों से ओल्ड एम्पायर नामक एक क्रूर साम्राज्य इस ग्रह को विद्रोहियों, विचारकों और स्वतंत्र आत्माओं की जेल के रूप में इस्तेमाल कर रहा है।",
    ),
    # Scene 9: Airl on The Electronic Amnesia Screen [ALIEN]
    AlienDocScene(
        scene_number=9,
        speaker="alien",
        visual_key="amnesia_screen",
        narration_en="A massive electronic force screen encircles this entire planet. When your biological body dies, an intense electronic shock erases all your past memories, forcing your soul back into a new biological body in an endless reincarnation amnesia trap.",
        narration_hi="पृथ्वी के चारों ओर एक विशाल इलेक्ट्रॉनिक जाल है। जब तुम्हारा शरीर मरता है, तो बिजली के भयानक झटके देकर तुम्हारी आत्मा की सारी यादें मिटा दी जाती हैं, और तुम्हें फिर से जन्म लेने के भूलभुलैया वाले चक्रव्यूह में कैद कर दिया जाता है।",
    ),
    # Scene 10: Narrator on Military Torture, Departure & Matilda's Legacy [NARRATOR]
    AlienDocScene(
        scene_number=10,
        speaker="narrator",
        visual_key="documents",
        narration_en="Terrified by Airl's revelations, military officers attempted electroshock interrogations, prompting Airl to sever her telepathic connection and abandon the doll body. Before her death in 2007, Nurse Matilda mailed these transcripts to the world. For more declassified extraterrestrial files and informative documentaries like this, please like, subscribe, and support our channel.",
        narration_hi="एयरल के खुलासों से घबराकर सेना के अफसरों ने उस पर बिजली के टॉर्चर किए, जिसके बाद एयरल शरीर छोड़कर लौट गई। अपनी मृत्यु से पहले नर्स मटिल्डा ने ये सभी गुप्त दस्तावेज दुनिया के सामने भेज दिए। ऐसे ही डीक्लासिफाइड और रहस्यमयी इंफॉर्मेटिव वीडियोज़ के लिए वीडियो को लाइक और सब्सक्राइब करें और हमें ज़रूर सपोर्ट करें।",
    ),
]


def make_documentary_widescreen(src_path: Path, out_path: Path, width: int = 1920, height: int = 1080) -> Path:
    """Format portrait photo into a cinematic 16:9 documentary image with blurred background."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not src_path.exists():
        return out_path

    src = Image.open(src_path).convert("RGB")
    sw, sh = src.size
    aspect_target = width / height
    aspect_src = sw / sh

    if aspect_src > aspect_target:
        new_h = height
        new_w = int(height * aspect_src)
    else:
        new_w = width
        new_h = int(width / aspect_src)

    bg = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    bg = bg.crop((left, top, left + width, top + height))
    bg = bg.filter(ImageFilter.GaussianBlur(35))
    bg = ImageEnhance.Brightness(bg).enhance(0.35)

    # Foreground: fit height to 1080
    fg_h = height
    fg_w = int(sw * (height / sh))
    fg = src.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

    paste_x = (width - fg_w) // 2
    bg.paste(fg, (paste_x, 0))
    bg.save(out_path, quality=95)
    return out_path


class AlienFullDocumentaryProducer:
    """Produces the definitive 16:9 master full documentary for Alien Interview."""

    def __init__(self):
        self.cfg = get_config()
        self.stock_fetcher = StockFetcher()
        self.bgm_manager = BackgroundMusicManager()
        self.tts = TTSEngine()
        self.builder = LongformBuilder()
        self.thumb_gen = ThumbnailGenerator()

    def prepare_visual_assets(self) -> List[Path]:
        """Prepare exactly matched 1920x1080 widescreen assets for all 10 scenes."""
        scenes_dir = self.cfg.paths.output_dir / "alien_scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        assets_alien = PROJECT_ROOT / "assets" / "alien_interview"
        temp_dir = self.cfg.paths.temp_dir

        # Scene 1: Roswell UFO Crash
        s1 = temp_dir / "stock_ufo_flying_sky_night_12936951.mp4"
        if not s1.exists():
            s1 = self.stock_fetcher.fetch_best_visual_for_scene("ufo flying sky night desert", output_dir=temp_dir, orientation="landscape")

        # Scene 2: Nurse Matilda at Wooden Interrogation Desk
        s2 = scenes_dir / "scene_02_matilda_doc.jpg"
        make_documentary_widescreen(assets_alien / "nurse_matilda.jpg", s2)

        # Scene 3: Alien Airl Macro Close-Up
        s3 = scenes_dir / "scene_03_airl_doc.jpg"
        make_documentary_widescreen(assets_alien / "airl_portrait.jpg", s3)

        # Scene 4: The Domain Starship Armada
        s4 = scenes_dir / "scene_04_domain_doc.jpg"
        make_documentary_widescreen(assets_alien / "domain_fleet_vision.jpg", s4)

        # Scene 5: Synthetic Doll Body Examination
        s5 = scenes_dir / "scene_05_synthetic_doc.jpg"
        make_documentary_widescreen(assets_alien / "airl_speaking.jpg", s5)

        # Scene 6: IS-BE (Luminous Ethereal Soul in Deep Space)
        s6 = temp_dir / "stock_glowing_nebula_39598754.mp4"
        if not s6.exists():
            s6 = temp_dir / "stock_milky_way_galaxy_39576931.mp4"
        if not s6.exists():
            s6 = self.stock_fetcher.fetch_best_visual_for_scene("glowing human soul ethereal cosmos", output_dir=temp_dir, orientation="landscape")

        # Scene 7: Building 84 Interrogation Two-Shot
        s7 = scenes_dir / "scene_07_twoshot_doc.jpg"
        make_documentary_widescreen(assets_alien / "interrogation_twoshot.jpg", s7)

        # Scene 8: Earth as a Cosmic Prison Planet (Encircled by Grid)
        s8 = temp_dir / "stock_earth_space_electric_grid_34707892.mp4"
        if not s8.exists():
            s8 = self.stock_fetcher.fetch_best_visual_for_scene("earth space electric grid barrier", output_dir=temp_dir, orientation="landscape")

        # Scene 9: The Electronic Amnesia Screen (Matrix Digital Code)
        s9 = temp_dir / "stock_matrix_code_digital_cyber_852292.mp4"
        if not s9.exists():
            s9 = self.stock_fetcher.fetch_best_visual_for_scene("matrix digital cyber electric grid", output_dir=temp_dir, orientation="landscape")

        # Scene 10: Top Secret Debriefing Documents & Generals
        s10 = scenes_dir / "scene_10_documents_doc.jpg"
        make_documentary_widescreen(assets_alien / "roswell_documents.jpg", s10)

        scene_assets = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10]
        for idx, a in enumerate(scene_assets):
            print_info(f"Scene {idx+1} ({CANONICAL_FULL_DOC_SCENES[idx].speaker.upper()}): {a.name}")
        return scene_assets

    def mix_master_soundtrack(
        self,
        voice_path: Path,
        output_mixed_path: Path,
        t1_bell: float,
        t2_bell: float,
    ) -> Path:
        """Mix voice narration with Rahasyamayi BGM ('the_complex.mp3') and Subscribe Bell Ding SFX."""
        bgm_path = PROJECT_ROOT / "assets" / "audio" / "alien" / "the_complex.mp3"
        if not bgm_path.exists():
            bgm_path = PROJECT_ROOT / "assets" / "audio" / "alien" / "roswell_mystery_calm.mp3"

        bell_sfx = PROJECT_ROOT / "assets" / "audio" / "youtube_bell_ding.wav"
        duration = get_media_duration(voice_path)

        d1_ms = int(max(0, t1_bell + 0.2) * 1000)
        d2_ms = int(max(0, t2_bell + 0.2) * 1000)

        print_info(f"Mixing Rahasyamayi BGM ({bgm_path.name}) with Bell Ding SFX at {t1_bell:.1f}s and {t2_bell:.1f}s...")

        # FFmpeg filter complex: Voice + looped lowpass BGM + 2 delayed bell chimes
        cmd = [
            "-i", str(voice_path),
            "-i", str(bgm_path),
            "-i", str(bell_sfx),
            "-i", str(bell_sfx),
            "-filter_complex",
            (
                "[0:a]volume=1.0[voice];"
                f"[1:a]aloop=loop=-1:size=2e+09,lowpass=f=3200,volume=0.13,afade=t=in:st=0:d=2.0,afade=t=out:st={duration-2.0:.2f}:d=2.0[bgm];"
                f"[2:a]adelay={d1_ms}|{d1_ms},volume=0.45[bell1];"
                f"[3:a]adelay={d2_ms}|{d2_ms},volume=0.45[bell2];"
                "[voice][bgm][bell1][bell2]amix=inputs=4:duration=first:dropout_transition=2[a_out]"
            ),
            "-map", "[a_out]",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(output_mixed_path),
        ]
        run_ffmpeg(cmd, desc="Mixing master audio with eerie BGM and bell sound effects")
        return output_mixed_path

    def composite_video_with_engagement(
        self,
        input_video: Path,
        subtitles_file: Path,
        output_video: Path,
        t1: float,
        t2: float,
    ) -> bool:
        """Burn subtitles and overlay Subscribe+Like+Bell visual banner at t1 and t2."""
        banner_path = PROJECT_ROOT / "assets" / "like_subscribe_bell_banner.png"
        fonts_dir = PROJECT_ROOT / "assets" / "fonts"

        from autotube.video.subtitle_burner import format_ffmpeg_subtitle_path
        sub_path_str = format_ffmpeg_subtitle_path(subtitles_file)
        fonts_dir_str = format_ffmpeg_subtitle_path(fonts_dir)

        # Force clean 16:9 widescreen subtitle styling
        force_style = "Fontname=Arial,Bold=1,Fontsize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=1,MarginV=35"

        sub_filter = f"subtitles='{sub_path_str}':fontsdir='{fonts_dir_str}':force_style='{force_style}'"

        banner_enable = f"between(t,{t1:.1f},{t1+4.2:.1f})+between(t,{t2:.1f},{t2+4.2:.1f})"
        overlay_filter = f"overlay=(W-w)/2:H-h-75:enable='{banner_enable}'"

        cmd = [
            "-i", str(input_video),
            "-i", str(banner_path),
            "-filter_complex", f"[0:v]{sub_filter}[v_sub];[v_sub][1:v]{overlay_filter}[v_out]",
            "-map", "[v_out]",
            "-map", "0:a",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "copy",
            str(output_video),
        ]
        return run_ffmpeg(cmd, desc="Burning subtitles and Subscribe+Like+Bell visual overlays")

    def produce(
        self,
        language: str = "both",
        upload: bool = False,
        privacy: str = "public",
    ) -> Dict[str, Path]:
        """Produce the full 16:9 documentary with authentic dialogue, rahasyamayi BGM, and popups."""
        print_banner()
        print_panel(
            "[bold cyan]Alien Interview Master 16:9 Full Documentary Production (Rev 2)[/bold cyan]\n"
            f"• Script Mode: [bold yellow]Authentic Character Dialogue (Matilda + Airl + Narrator)[/bold yellow]\n"
            f"• Sound Design: [bold magenta]Rahasyamayi Eerie BGM ('the_complex.mp3') + Dynamic Bell Ding SFX[/bold magenta]\n"
            f"• Visual Popups: [bold green]Subscribe + Like + Bell Visual Banner at Scene Transitions[/bold green]\n"
            f"• Scene Matching: [bold white]100% Exact 1-to-1 Spoken Words Alignment across all 10 Scenes[/bold white]\n"
            f"• Languages: [bold cyan]{language.upper()}[/bold cyan]",
            title="Refined Video Production Initialized",
        )

        temp_dir = self.cfg.paths.temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)
        videos_dir = self.cfg.paths.output_dir / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)

        do_en = language.lower() in ("both", "en", "english", "all")
        do_hi = language.lower() in ("both", "hi", "hindi", "all")

        # Step 1: Prepare exactly matched 16:9 landscape visual assets
        print_step(1, 4, "Preparing 100% Word-Matched 16:9 Widescreen Scene Assets")
        scene_visuals = self.prepare_visual_assets()

        results: Dict[str, Path] = {}

        class SceneObj:
            def __init__(self, spk, narr, num):
                self.speaker = spk
                self.narration = narr
                self.scene_number = num

        # -------------------------------------------------------------
        # Step 2: English Master Edition
        # -------------------------------------------------------------
        if do_en:
            print_step(2, 4, "Producing English Master Documentary (1920x1080)")
            en_slug = "roswell_alien_interview_full_en"

            en_scene_objs = [
                SceneObj(s.speaker, s.narration_en, s.scene_number)
                for s in CANONICAL_FULL_DOC_SCENES
            ]

            raw_voice_en = temp_dir / f"{en_slug}_voice_raw.mp3"
            tts_res_en = self.tts.synthesize_dialogue(
                scenes=en_scene_objs,
                output_audio_path=raw_voice_en,
                language="en",
            )

            # Determine timestamps for Subscribe + Like + Bell popups
            durations = tts_res_en.scene_durations
            t1_en = sum(durations[:4])  # Transition into Scene 5
            t2_en = sum(durations[:9])  # Transition into Scene 10

            # Mix with Rahasyamayi BGM and Bell Chime SFX
            master_audio_en = temp_dir / f"{en_slug}_master_audio.mp3"
            self.mix_master_soundtrack(
                voice_path=tts_res_en.audio_path,
                output_mixed_path=master_audio_en,
                t1_bell=t1_en,
                t2_bell=t2_en,
            )

            # Build raw 16:9 widescreen video
            raw_video_en = temp_dir / f"raw_{en_slug}.mp4"
            self.builder.build_video(
                audio_path=master_audio_en,
                scene_visuals=scene_visuals,
                output_path=raw_video_en,
                subtitles_file=None,  # Handled with custom placement below
                scene_durations=durations,
            )

            # Burn Subtitles & Subscribe/Like/Bell Visual Overlays
            output_video_en = videos_dir / f"{en_slug}.mp4"
            self.composite_video_with_engagement(
                input_video=raw_video_en,
                subtitles_file=tts_res_en.subtitles_ass_path,
                output_video=output_video_en,
                t1=t1_en,
                t2=t2_en,
            )

            # Generate High-CTR Thumbnail
            thumb_en = videos_dir / f"{en_slug}_thumb.jpg"
            thumb_bg = PROJECT_ROOT / "assets" / "alien_interview" / "airl_portrait.jpg"
            self.thumb_gen.generate_thumbnail(
                title="1947 ROSWELL ALIEN INTERVIEW: THE COMPLETE LEAKED INTERROGATION",
                output_path=thumb_en,
                background_image=thumb_bg,
            )

            if output_video_en.exists():
                results["en"] = output_video_en
                print_success(f"English Master Documentary Ready: {output_video_en.name} ({output_video_en.stat().st_size / (1024*1024):.1f} MB)")

        # -------------------------------------------------------------
        # Step 3: Hindi Master Edition
        # -------------------------------------------------------------
        if do_hi:
            print_step(3, 4, "Producing Hindi Master Documentary (1920x1080)")
            hi_slug = "roswell_alien_interview_full_hi"

            hi_scene_objs = [
                SceneObj(s.speaker, s.narration_hi, s.scene_number)
                for s in CANONICAL_FULL_DOC_SCENES
            ]

            raw_voice_hi = temp_dir / f"{hi_slug}_voice_raw.mp3"
            tts_res_hi = self.tts.synthesize_dialogue(
                scenes=hi_scene_objs,
                output_audio_path=raw_voice_hi,
                language="hi",
            )

            # Determine timestamps for Subscribe + Like + Bell popups
            durations_hi = tts_res_hi.scene_durations
            t1_hi = sum(durations_hi[:4])  # Transition into Scene 5
            t2_hi = sum(durations_hi[:9])  # Transition into Scene 10

            # Mix with Rahasyamayi BGM and Bell Chime SFX
            master_audio_hi = temp_dir / f"{hi_slug}_master_audio.mp3"
            self.mix_master_soundtrack(
                voice_path=tts_res_hi.audio_path,
                output_mixed_path=master_audio_hi,
                t1_bell=t1_hi,
                t2_bell=t2_hi,
            )

            # Build raw 16:9 widescreen video
            raw_video_hi = temp_dir / f"raw_{hi_slug}.mp4"
            self.builder.build_video(
                audio_path=master_audio_hi,
                scene_visuals=scene_visuals,
                output_path=raw_video_hi,
                subtitles_file=None,
                scene_durations=durations_hi,
            )

            # Burn Subtitles & Subscribe/Like/Bell Visual Overlays
            output_video_hi = videos_dir / f"{hi_slug}.mp4"
            self.composite_video_with_engagement(
                input_video=raw_video_hi,
                subtitles_file=tts_res_hi.subtitles_ass_path,
                output_video=output_video_hi,
                t1=t1_hi,
                t2=t2_hi,
            )

            # Generate High-CTR Thumbnail
            thumb_hi = videos_dir / f"{hi_slug}_thumb.jpg"
            thumb_bg = PROJECT_ROOT / "assets" / "alien_interview" / "airl_portrait.jpg"
            self.thumb_gen.generate_thumbnail(
                title="रोसवेल 1947: एलियन इंटरव्यू का पूरा सच [FULL DOCUMENTARY]",
                output_path=thumb_hi,
                background_image=thumb_bg,
            )

            if output_video_hi.exists():
                results["hi"] = output_video_hi
                print_success(f"Hindi Master Documentary Ready: {output_video_hi.name} ({output_video_hi.stat().st_size / (1024*1024):.1f} MB)")

        print_step(4, 4, "Refined Full Documentary Production Complete!")
        return results
