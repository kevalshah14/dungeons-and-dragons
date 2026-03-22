from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import Difficulty


class DiceCheck(BaseModel):
    ability: str = Field(description="Which ability score to roll against (e.g. 'strength', 'dexterity').")
    difficulty_class: int = Field(description="The DC (difficulty class) number to beat.", ge=1, le=30)
    success_outcome: str = Field(description="What happens on a successful roll.")
    failure_outcome: str = Field(description="What happens on a failed roll.")


class Choice(BaseModel):
    choice_id: str = Field(description="Unique identifier for this choice (e.g. 'c1_a').")
    description: str = Field(description="What the players choose to do.")
    dice_check: Optional[DiceCheck] = Field(default=None, description="Optional dice roll required.")
    leads_to: str = Field(description="The scene_id this choice leads to.")
    risk_level: Difficulty = Field(description="How risky this choice is.")


class Scene(BaseModel):
    scene_id: str = Field(description="Unique identifier for this scene (e.g. 'scene_1', 'scene_2a').")
    title: str = Field(description="Short title for this scene.")
    narrative: str = Field(description="The DM's narration for this scene, describing what the players see and experience.")
    choices: list[Choice] = Field(default_factory=list, description="Available choices. Empty list means this is an ending.")
    is_ending: bool = Field(default=False, description="Whether this scene is a final ending.")
    ending_type: Optional[str] = Field(default=None, description="If ending: 'victory', 'defeat', or 'bittersweet'.")


class GameTree(BaseModel):
    root_scene_id: str = Field(description="The scene_id where the adventure begins.")
    scenes: list[Scene] = Field(description="All scenes in the decision tree.")
    total_endings: int = Field(description="How many different endings exist.")
    critical_path_length: int = Field(description="Minimum number of scenes to reach an ending.")
