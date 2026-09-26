"""Script generation models and schemas."""

from typing import List, Optional
from pydantic import BaseModel, Field


class Scene(BaseModel):
    scene_number: int
    narration: str = Field(description="The spoken narration for this scene")
    visual_query: str = Field(
        description="Search keywords for stock footage or AI image (e.g. 'space rocket launching cinematic')"
    )
    visual_description: str = Field(
        description="Description of what should appear on screen"
    )
    estimated_duration_sec: float = Field(
        default=5.0, description="Estimated duration in seconds"
    )


class ShortScript(BaseModel):
    title: str = Field(description="Catchy, high-CTR title for YouTube Shorts")
    topic: str
    hook: str = Field(description="First 3 seconds hook sentence that grabs attention")
    narration: str = Field(
        description="Full continuous narration text for voiceover without scene markers"
    )
    call_to_action: str = Field(
        default="Subscribe for more mind-blowing facts!",
        description="Outro / call to action",
    )
    visual_keywords: List[str] = Field(
        default_factory=list,
        description="Keywords to fetch matching stock videos or AI backgrounds",
    )
    tags: List[str] = Field(
        default_factory=lambda: ["#Shorts", "#viral", "#trending"]
    )
    pinned_comment: Optional[str] = Field(
        default="What would you do if this happened? Let me know in the comments below! 👇",
        description="A provocative question to pin in the comments to maximize engagement",
    )
    estimated_duration_sec: int = Field(default=50)


class LongVideoScript(BaseModel):
    title: str = Field(description="Clickable, engaging YouTube Video Title")
    topic: str
    description: str = Field(
        description="Full YouTube video description with timestamps, summary, and links"
    )
    tags: List[str] = Field(
        default_factory=list, description="Targeted SEO tags for the video"
    )
    scenes: List[Scene] = Field(
        description="Ordered list of scenes comprising the entire video"
    )
    total_estimated_duration_sec: int = Field(default=300)

    @property
    def full_narration(self) -> str:
        """Combine all scene narrations into one continuous voiceover string."""
        return "\n\n".join(scene.narration for scene in self.scenes)
