from pydantic import BaseModel, Field

from src.models.enums import Difficulty


class NPC(BaseModel):
    name: str = Field(description="The NPC's full name.")
    role: str = Field(description="Their role in the story (e.g. 'villain', 'quest giver', 'merchant').")
    description: str = Field(description="A brief physical and personality description.")
    motivation: str = Field(description="What drives this NPC.")


class Location(BaseModel):
    name: str = Field(description="Name of the location.")
    description: str = Field(description="Vivid description of the location.")
    danger_level: Difficulty = Field(description="How dangerous this location is.")
    notable_features: list[str] = Field(description="Key things players would notice here.")


class Story(BaseModel):
    title: str = Field(description="An evocative title for the adventure.")
    setting: str = Field(description="The world/region where this adventure takes place.")
    backstory: str = Field(description="The history and events leading up to the adventure.")
    main_quest: str = Field(description="The overarching goal the players must accomplish.")
    hooks: list[str] = Field(description="Plot hooks that draw the players into the adventure, one per player.")
    key_locations: list[Location] = Field(description="Important locations in the adventure.")
    key_npcs: list[NPC] = Field(description="Important non-player characters.")
    difficulty: Difficulty = Field(description="Overall difficulty of the adventure.")
    estimated_sessions: int = Field(description="Estimated number of play sessions to complete.")
