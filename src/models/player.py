from typing import Optional

from pydantic import BaseModel, Field

from src.models.enums import Race, CharacterClass


class AbilityScores(BaseModel):
    strength: int = Field(description="Physical power. Range 3-18.", ge=3, le=18)
    dexterity: int = Field(description="Agility and reflexes. Range 3-18.", ge=3, le=18)
    constitution: int = Field(description="Endurance and health. Range 3-18.", ge=3, le=18)
    intelligence: int = Field(description="Knowledge and reasoning. Range 3-18.", ge=3, le=18)
    wisdom: int = Field(description="Perception and insight. Range 3-18.", ge=3, le=18)
    charisma: int = Field(description="Force of personality. Range 3-18.", ge=3, le=18)


class Player(BaseModel):
    name: str = Field(description="The character's full name.")
    race: Race = Field(description="The character's race/species.")
    character_class: CharacterClass = Field(description="The character's class (their 'job').")
    backstory: str = Field(description="A compelling backstory that ties into the adventure.")
    ability_scores: AbilityScores = Field(description="The six core ability scores.")
    hit_points: int = Field(description="Starting hit points.", ge=1)
    armor_class: int = Field(description="Base armor class.", ge=1)
    abilities: list[str] = Field(description="Special abilities and skills from race and class.")
    inventory: list[str] = Field(description="Starting equipment and items.")
    personality_traits: list[str] = Field(description="2-3 personality quirks that make this character unique.")
    level: int = Field(default=1, description="Character level.")


class Party(BaseModel):
    players: list[Player] = Field(description="All player characters in the party.")
    party_name: Optional[str] = Field(default=None, description="An optional party/group name.")
    shared_goal: str = Field(description="What unites this group of adventurers.")
