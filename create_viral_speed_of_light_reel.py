"""Generate a viral 55-60s Reel on 'Surya Siddhanta & Speed of Light' using OpenMontage Remotion Engine.
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from autotube.video.remotion_bridge import RemotionBridge
from autotube.uploader.facebook_upload import FacebookReelsUploader
from autotube.utils.console import print_info, print_success, print_error, print_warning

TITLE = "प्रकाश की गति का प्राचीन रहस्य: ऋषियों ने हज़ारों साल पहले इसे कैसे नापा?"
HOOK_TEXT = "प्रकाश की गति का वैदिक रहस्य?!"

SCRIPT = """क्या आप जानते हैं, जिस 'Speed of Light' यानी प्रकाश की गति को आधुनिक विज्ञान ने 1970 के दशक में लेज़र तकनीक से 299,792 किलोमीटर प्रति सेकंड नापा,
वो बात 14वीं सदी के महान विद्वान सायण ने ऋग्वेद के एक श्लोक के भाष्य में शब्द-दर-शब्द लिख दी थी!
श्लोक में लिखा है: 'योजनानां सहस्रे द्वे द्वे शते द्वे च योजने, एकेन निमिषार्धेन क्रममाण नमोऽस्तु ते।'
इसका अर्थ है: प्रकाश आधे निमेष के समय में 2202 योजन की दूरी तय करता है।
प्राचीन वैदिक माप के अनुसार, 1 योजन लगभग 9 मील और 1 निमेष 16/75 सेकंड का समय होता है।
जब आधुनिक भौतिकविदों ने इस प्राचीन सूत्र का हिसाब लगाया, तो उत्तर आया ठीक 187,670 मील प्रति सेकंड!
जो आज की आधुनिक गति 186,282 मील प्रति सेकंड के 99.9% आश्चर्यजनक रूप से करीब है!
बिना किसी टेलीस्कोप या आधुनिक मशीन के प्राचीन ऋषियों की यह सटीक गणना क्या सिर्फ संयोग हो सकती है? अपनी राय कमेंट में ज़रूर बताएं और ऐसे ही प्राचीन विज्ञान के रहस्यों के लिए CosmoChronicle को फॉलो करें!"""

def main():
    print_info("=" * 65)
    print_info("🚀 Starting OpenMontage Viral Reel: Surya Siddhanta & Speed of Light")
    print_info(f"📌 Page: CosmoChronicle | Target: Facebook Reels & YouTube Shorts")
    print_info("=" * 65)

    bridge = RemotionBridge()

    t0 = time.time()
    try:
        final_video_path = bridge.render_reel(
            title=TITLE,
            script_text=SCRIPT,
            voice="Charon",
            hook_text=HOOK_TEXT,
            output_format="vertical_9x16",
            enable_subscribe_cta=True,
            target_platform="facebook",
        )
    except Exception as e:
        print_error(f"Render failed: {e}")
        sys.exit(1)

    render_duration = time.time() - t0
    print_success(f"🎬 Reel Rendered Successfully in {render_duration/60:.1f} minutes! File: {final_video_path}")

    # Web Streaming Optimization (Faststart & CRF 22 for instant web play)
    try:
        opt_path = final_video_path.with_name(f"{final_video_path.stem}_web.mp4")
        print_info(f"⚡ Applying FastStart & Web Optimization -> {opt_path.name}...")
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", str(final_video_path),
            "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
            "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "128k",
            str(opt_path)
        ]
        res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if res.returncode == 0 and opt_path.exists():
            final_video_path = opt_path
            print_success(f"✨ FastStart Web Video Created ({opt_path.stat().st_size / (1024*1024):.1f} MB)!")
    except Exception as opt_err:
        print_warning(f"Optimization notice: {opt_err}")

    # Publish to Facebook Page (CosmoChronicle)
    print_info("\n📤 Publishing Reel to Facebook Page 'CosmoChronicle'...")
    fb = FacebookReelsUploader()
    if not fb.is_configured():
        print_warning("Facebook Page credentials not configured; video saved locally.")
        return

    caption = (
        "प्रकाश की गति (Speed of Light) का प्राचीन वैदिक रहस्य! ☀️⚡\n\n"
        "14वीं सदी में सायण भाष्य और ऋग्वेद में दर्ज वो गणना जो आधुनिक लेज़र फिजिक्स (299,792 km/s) से 99.9% मैच करती है। "
        "क्या यह सिर्फ संयोग है या हमारे पूर्वजों का उन्नत खगोल विज्ञान? 🤔✨\n\n"
        "फॉलो करें @CosmoChronicle ऐसे ही अविश्वसनीय ब्रह्मांडीय और प्राचीन विज्ञान के रहस्यों के लिए!\n\n"
        "#SpeedOfLight #SuryaSiddhanta #VedicScience #Rigveda #AncientIndia #CosmoChronicle #ScienceMystery #ViralReels #ReelsIndia #IndianAstronomy"
    )

    tags = ["SpeedOfLight", "SuryaSiddhanta", "VedicScience", "Rigveda", "AncientAstronomy", "CosmoChronicle"]

    upload_res = fb.upload_reel(
        video_path=final_video_path,
        title=TITLE,
        description=caption,
        tags=tags,
    )

    if upload_res.get("success"):
        reel_id = upload_res.get("video_id") or upload_res.get("id")
        page_name = upload_res.get("page_name", "CosmoChronicle")
        print_success(f"🎉 Reel successfully published to Facebook Page '{page_name}'! Reel ID: {reel_id}")
    else:
        print_error(f"Facebook upload status: {upload_res.get('error')}")

if __name__ == "__main__":
    main()
