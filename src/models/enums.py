from enum import Enum


class Race(str, Enum):
    HUMAN = "Human"
    ELF = "Elf"
    DWARF = "Dwarf"
    HALFLING = "Halfling"
    HALF_ORC = "Half-Orc"
    GNOME = "Gnome"
    TIEFLING = "Tiefling"
    DRAGONBORN = "Dragonborn"


class CharacterClass(str, Enum):
    FIGHTER = "Fighter"
    WIZARD = "Wizard"
    CLERIC = "Cleric"
    ROGUE = "Rogue"
    RANGER = "Ranger"
    PALADIN = "Paladin"
    BARD = "Bard"
    BARBARIAN = "Barbarian"
    SORCERER = "Sorcerer"
    WARLOCK = "Warlock"
    DRUID = "Druid"
    MONK = "Monk"


class Difficulty(str, Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    DEADLY = "Deadly"
