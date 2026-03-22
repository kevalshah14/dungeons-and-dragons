from typing import Optional

from pydantic import BaseModel, Field


class ActionOption(BaseModel):
    description: str = Field(description="What this player can do. Short and clear.")
    ability_check: Optional[str] = Field(
        default=None,
        description="The ability to roll against, e.g. 'strength', 'dexterity', 'charisma'. Null if no roll needed.",
    )
    difficulty_class: Optional[int] = Field(
        default=None,
        description="The DC number to beat. Null if no roll needed.",
        ge=1,
        le=30,
    )
    damage_on_fail: Optional[int] = Field(
        default=None,
        description="How much HP the player loses if they fail. Null if safe.",
    )
    is_attack: bool = Field(
        default=False,
        description="True if this is an attack on an enemy.",
    )


class DialogueLine(BaseModel):
    character: str = Field(
        description="The exact name of who is speaking (NPC name or player name)."
    )
    line: str = Field(
        description="What they say. Short and in character. 1-2 sentences max."
    )


class DynamicScene(BaseModel):
    title: str = Field(description="Short title for this scene.")
    narrative: str = Field(
        description=(
            "Tell the story of what just happened. Write it like a book -- "
            "describe actions, sounds, feelings. 3-6 sentences. "
            "Name each character. Show how one player's action affects the other. "
            "End with what the active player sees or faces right now. "
            "Do NOT put character dialogue here -- put it in the dialogue list instead."
        )
    )
    dialogue: list[DialogueLine] = Field(
        default_factory=list,
        description=(
            "Characters who SPEAK in this scene. NPCs, players reacting, villains taunting. "
            "1-3 lines max. Only include dialogue that matters to the story. "
            "Each line should sound like that character -- villains are mean, "
            "quest givers are worried, rogues are sarcastic, fighters are bold."
        ),
    )
    active_player: str = Field(
        description=(
            "The name of the player who acts THIS turn. "
            "Pick based on who the story naturally focuses on right now."
        )
    )
    situation: str = Field(
        description="What the active player faces right now. 1-2 short sentences."
    )
    options: list[ActionOption] = Field(
        default_factory=list,
        description=(
            "2-3 things the active player can do. "
            "At least one safe (no roll) and one risky (with roll). "
            "Empty list means this is an ending."
        ),
    )
    is_ending: bool = Field(default=False, description="True if the adventure is over.")
    ending_type: Optional[str] = Field(
        default=None, description="If ending: 'victory', 'defeat', or 'bittersweet'."
    )


class TurnRecord(BaseModel):
    turn: int = Field(description="Turn number.")
    scene_title: str = Field(description="Title of the scene.")
    narrative: str = Field(description="The story narration.")
    chosen_action: str = Field(description="What the player chose to do.")
    player_who_acted: str = Field(description="Name of the player who acted.")
    ability_checked: Optional[str] = Field(default=None)
    dice_roll: Optional[int] = Field(default=None)
    dice_modifier: Optional[int] = Field(default=None)
    proficiency_bonus: Optional[int] = Field(default=None)
    dice_total: Optional[int] = Field(default=None)
    difficulty_class: Optional[int] = Field(default=None)
    succeeded: Optional[bool] = Field(default=None)
    was_critical: bool = Field(default=False)
    was_fumble: bool = Field(default=False)
    damage_taken: int = Field(default=0)
    hp_after: Optional[int] = Field(default=None)
