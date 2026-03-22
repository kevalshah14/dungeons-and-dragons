from pydantic import BaseModel, Field

from src.models.story import Story
from src.models.player import Party
from src.models.game_tree import GameTree


class GameState(BaseModel):
    story: Story
    party: Party
    game_tree: GameTree
    current_scene_id: str = Field(description="Which scene the players are currently in.")
