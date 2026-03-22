from typing import Optional

from pydantic import BaseModel, Field

from src.models.story import Story
from src.models.player import Party
from src.models.game_tree import DynamicScene, TurnRecord


class GameState(BaseModel):
    story: Story
    party: Party
    history: list[TurnRecord] = Field(default_factory=list, description="Log of all turns played.")
    current_scene: Optional[DynamicScene] = Field(default=None, description="The current scene.")
    turn_number: int = Field(default=0, description="Current turn number.")
    is_over: bool = Field(default=False, description="Whether the game has ended.")
    player_hp: dict[str, int] = Field(
        default_factory=dict,
        description="Current HP for each player, keyed by player name.",
    )

    def init_hp(self):
        """Set each player's current HP to their max from the party sheet."""
        for p in self.party.players:
            self.player_hp[p.name] = p.hit_points

    def get_hp(self, name: str) -> int:
        return self.player_hp.get(name, 0)

    def apply_damage(self, name: str, amount: int) -> int:
        """Reduce a player's HP by amount (min 0). Returns new HP."""
        current = self.player_hp.get(name, 0)
        new_hp = max(0, current - amount)
        self.player_hp[name] = new_hp
        return new_hp

    def heal(self, name: str, amount: int) -> int:
        """Heal a player by amount (capped at max HP). Returns new HP."""
        max_hp = next((p.hit_points for p in self.party.players if p.name == name), 0)
        current = self.player_hp.get(name, 0)
        new_hp = min(max_hp, current + amount)
        self.player_hp[name] = new_hp
        return new_hp

    def is_conscious(self, name: str) -> bool:
        return self.player_hp.get(name, 0) > 0

    def all_knocked_out(self) -> bool:
        return all(hp <= 0 for hp in self.player_hp.values())
