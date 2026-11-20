"""Complete Orchestration Pipeline for Daily Trending News & Facebook Feed Posts.
Discovers viral news -> Generates Hindi script & poll -> Renders 1080x1080 card -> Publishes to Facebook.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from autotube.config import PROJECT_ROOT
from autotube.news.news_card_generator import NewsCardGenerator
from autotube.news.news_post_generator import NewsPostGenerator
from autotube.news.trending_collector import TrendingNewsCollector
from autotube.uploader.facebook_upload import FacebookReelsUploader
from autotube.utils.console import print_error, print_info, print_success, print_warning

logger = logging.getLogger(__name__)

POSTS_LOG_FILE = PROJECT_ROOT / "config" / "facebook_news_posts_history.json"


class DailyNewsPostPipeline:
    """Manages end-to-end creation and automated publishing of daily Facebook news posts."""

    def __init__(self):
        self.collector = TrendingNewsCollector()
        self.post_gen = NewsPostGenerator()
        self.card_gen = NewsCardGenerator()
        self.fb_uploader = FacebookReelsUploader()

    def run(
        self,
        publish: bool = True,
        override_topic: Optional[str] = None,
        override_image: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute full daily news post pipeline.
        
        Args:
            publish: Whether to upload immediately to Facebook Page feed.
            override_topic: Optional topic string to force specific news (e.g. 'NVIDIA CEO Jensen Huang').
            override_image: Optional local image path to use instead of web scraping.
        """
        print_info("🚀 Starting Daily Facebook News Post Pipeline...")

        # 1. Collect or prepare story
        if override_topic:
            print_info(f"Using override topic: {override_topic}")
            story = {
                "headline_en": override_topic,
                "category": "TECH & AI UPDATE",
                "tag_hindi": "ताज़ा टेक अपडेट",
                "subject": override_topic.split()[0],
                "summary": override_topic,
                "search_query": override_topic,
                "photo_credit": "Press / Global Media",
            }
            if override_image and Path(override_image).exists():
                story["image_path"] = str(override_image)
            else:
                photo_path = self.collector.fetch_high_res_photo(
                    search_query=override_topic,
                    subject=override_topic.split()[0],
                    category="TECH & AI UPDATE",
                    headline=override_topic,
                )
                story["image_path"] = str(photo_path) if photo_path else ""
        else:
            story = self.collector.get_todays_featured_story()

        raw_img = story.get("image_path")
        if not raw_img or not Path(raw_img).exists():
            print_info("Story image not found locally; executing smart photo retrieval...")
            photo_path = self.collector.fetch_high_res_photo(
                search_query=story.get("search_query", story.get("subject", "")),
                subject=story.get("subject", ""),
                category=story.get("category", ""),
                headline=story.get("headline_en", ""),
            )
            if photo_path and Path(photo_path).exists():
                raw_img = str(photo_path)
            else:
                # Themed categorical fallback
                fb_dir = PROJECT_ROOT / "assets" / "news_fallback"
                cat_lower = str(story.get("category", "")).lower()
                subj_lower = str(story.get("subject", "")).lower()
                hl_lower = str(story.get("headline_en", "")).lower()
                all_text = f"{cat_lower} {subj_lower} {hl_lower}"

                if "jensen" in all_text or "nvidia" in all_text:
                    fallback_file = fb_dir / "jensen_huang.jpg"
                elif "space" in all_text or "galaxy" in all_text or "mars" in all_text or "webb" in all_text:
                    fallback_file = fb_dir / "space_galaxy.jpg"
                elif "robot" in all_text or "automation" in all_text:
                    fallback_file = fb_dir / "robotics.jpg"
                elif "quantum" in all_text or "chip" in all_text or "semiconductor" in all_text:
                    fallback_file = fb_dir / "quantum_chip.jpg"
                elif "bio" in all_text or "dna" in all_text or "medical" in all_text or "health" in all_text:
                    fallback_file = fb_dir / "biotech_dna.jpg"
                elif "ai" in all_text or "intelligence" in all_text or "neural" in all_text:
                    fallback_file = fb_dir / "ai_neural.jpg"
                else:
                    fallback_file = fb_dir / "future_tech.jpg"

                if fallback_file.exists():
                    raw_img = str(fallback_file)
                    print_info(f"Using category fallback: {fallback_file.name}")
                else:
                    print_error("❌ Could not obtain high-resolution image for news card.")
                    return {"success": False, "error": "No image available for news card generation."}

        # 2. Generate Hindi Content & Poll
        print_info("✍️ Generating Hindi headline, breakdown & engagement poll...")
        post_content = self.post_gen.generate_post_content(story)

        # 3. Render 1080x1080 Card
        ts = int(time.time())
        card_dir = PROJECT_ROOT / "content" / "facebook"
        card_dir.mkdir(parents=True, exist_ok=True)
        card_path = card_dir / f"fb_news_card_{ts}.jpg"

        print_info("🎨 Rendering 1080x1080 Breaking News Card...")
        rendered_card = self.card_gen.render_card(
            image_path=Path(raw_img),
            content=post_content,
            output_path=card_path,
        )

        caption = post_content.get("post_caption", "")
        post_title = post_content.get("post_title", story.get("headline_en", "Trending News"))

        result = {
            "success": True,
            "title": post_title,
            "card_path": str(rendered_card),
            "caption": caption,
            "story": story,
            "facebook_published": False,
            "post_id": None,
            "post_url": None,
            "timestamp": ts,
        }

        # 4. Publish to Facebook if requested
        if publish and self.fb_uploader.is_configured():
            print_info("📤 Publishing news card to Facebook Page feed...")
            pub_res = self.fb_uploader.publish_photo(
                image_path=rendered_card,
                caption=caption,
            )
            if pub_res.get("success"):
                result["facebook_published"] = True
                result["post_id"] = pub_res.get("post_id")
                result["post_url"] = pub_res.get("post_url")
                print_success(f"🎉 News post live on Facebook: {result['post_url']}")
            else:
                result["facebook_error"] = pub_res.get("error")
                print_warning(f"Facebook publish did not complete: {pub_res.get('error')}")
        else:
            if not publish:
                print_info("ℹ️ Publish skipped (preview mode).")
            else:
                print_warning("Facebook credentials not configured; card saved locally.")

        self._record_post_history(result)
        return result

    @staticmethod
    def _record_post_history(entry: Dict[str, Any]) -> None:
        """Store post record in history json file."""
        try:
            POSTS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            history = []
            if POSTS_LOG_FILE.exists():
                with open(POSTS_LOG_FILE, "r", encoding="utf-8") as f:
                    try:
                        history = json.load(f)
                        if not isinstance(history, list):
                            history = []
                    except Exception:
                        history = []
            
            clean_entry = {
                "title": entry.get("title"),
                "card_path": entry.get("card_path"),
                "caption": entry.get("caption"),
                "facebook_published": entry.get("facebook_published", False),
                "post_id": entry.get("post_id"),
                "post_url": entry.get("post_url"),
                "timestamp": entry.get("timestamp", int(time.time())),
                "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            history.insert(0, clean_entry)
            history = history[:100]

            with open(POSTS_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Could not write news post history: {e}")


def run_daily_facebook_news_post(publish: bool = True) -> Dict[str, Any]:
    """Helper entry point for scheduler or CLI."""
    pipeline = DailyNewsPostPipeline()
    return pipeline.run(publish=publish)
