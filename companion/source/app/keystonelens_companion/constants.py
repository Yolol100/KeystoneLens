"""Season and UI constants for KeystoneLens Companion 0.12.8"""
from __future__ import annotations

# Verified legacy WCL encounter IDs. Season 2 is resolved dynamically from live WCL zone 55.
DUNGEONS: dict[str, int] = {
    "Algeth'ar Academy": 112526,
    "Magisters' Terrace": 12811,
    "Maisara Caverns": 12874,
    "Nexus-Point Xenas": 12915,
    "Pit of Saron": 10658,
    "Seat of the Triumvirate": 361753,
    "Skyreach": 61209,
    "Windrunner Spire": 12805,
}

ACTIVITY_TO_DUNGEON: dict[int, str] = {
    115: "Pit of Saron", 131: "Pit of Saron", 1769: "Pit of Saron", 1770: "Pit of Saron",
    24: "Skyreach", 32: "Skyreach", 182: "Skyreach", 404: "Skyreach",
    484: "Seat of the Triumvirate", 485: "Seat of the Triumvirate", 486: "Seat of the Triumvirate",
    1622: "Seat of the Triumvirate", 1644: "Seat of the Triumvirate",
    1157: "Algeth'ar Academy", 1158: "Algeth'ar Academy", 1159: "Algeth'ar Academy", 1160: "Algeth'ar Academy",
    1539: "Windrunner Spire", 1540: "Windrunner Spire", 1541: "Windrunner Spire", 1542: "Windrunner Spire",
    1757: "Magisters' Terrace", 1758: "Magisters' Terrace", 1759: "Magisters' Terrace", 1760: "Magisters' Terrace",
    1761: "Maisara Caverns", 1762: "Maisara Caverns", 1763: "Maisara Caverns", 1764: "Maisara Caverns",
    1765: "Nexus-Point Xenas", 1766: "Nexus-Point Xenas", 1767: "Nexus-Point Xenas", 1768: "Nexus-Point Xenas",
}

CLASS_NAMES: dict[int, str] = {
    1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest",
    6: "Death Knight", 7: "Shaman", 8: "Mage", 9: "Warlock", 10: "Monk",
    11: "Druid", 12: "Demon Hunter", 13: "Evoker",
}

SPEC_NAMES: dict[int, str] = {
    250: "Blood", 251: "Frost", 252: "Unholy",
    577: "Havoc", 581: "Vengeance", 1480: "Devourer",
    102: "Balance", 103: "Feral", 104: "Guardian", 105: "Restoration",
    1467: "Devastation", 1468: "Preservation", 1473: "Augmentation",
    253: "Beast Mastery", 254: "Marksmanship", 255: "Survival",
    62: "Arcane", 63: "Fire", 64: "Frost",
    268: "Brewmaster", 269: "Windwalker", 270: "Mistweaver",
    65: "Holy", 66: "Protection", 70: "Retribution",
    256: "Discipline", 257: "Holy", 258: "Shadow",
    259: "Assassination", 260: "Outlaw", 261: "Subtlety",
    262: "Elemental", 263: "Enhancement", 264: "Restoration",
    265: "Affliction", 266: "Demonology", 267: "Destruction",
    71: "Arms", 72: "Fury", 73: "Protection",
}

ROLE_NAMES = {0:"TANK", 1:"HEALER", 2:"DPS", 3:"DPS"}
HEALER_SPECS = frozenset({65, 105, 256, 257, 264, 270, 1468})
TANK_SPECS = frozenset({66, 73, 104, 250, 268, 581})
REGION_NAMES = {1:"US", 2:"KR", 3:"EU", 4:"TW", 5:"CN"}

# Readability-first overlay palette.
BG = "#0d1016"
PANEL = "#141923"
PANEL_ALT = "#11161f"
BORDER = "#2b3342"
TEXT = "#f3f5f7"
MUTED = "#9099a8"
ACCENT = "#5da8ff"
GREEN = "#52d273"
YELLOW = "#f1c75b"
ORANGE = "#f39a55"
RED = "#ef6b6b"
PURPLE = "#bc84ff"
