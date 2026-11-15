"""AutoTube News & Social Growth Package.
Handles automated collection of trending Tech, AI & Space news,
generates 1080x1080 breaking news cards, and publishes posts & stories to Facebook.
"""

from autotube.news.trending_collector import TrendingNewsCollector
from autotube.news.news_card_generator import NewsCardGenerator
from autotube.news.news_post_generator import NewsPostGenerator
from autotube.news.news_pipeline import DailyNewsPostPipeline

__all__ = [
    "TrendingNewsCollector",
    "NewsCardGenerator",
    "NewsPostGenerator",
    "DailyNewsPostPipeline",
]
