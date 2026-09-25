from __future__ import annotations

# Verified Warcraft Logs Mythic+ encounter IDs.
DUNGEONS: dict[str, int] = {
    "Algeth'ar Academy": 112526,
    "Magisters' Terrace": 12811,
    "Maisara Caverns": 12874,
    "Nexus-Point Xenas": 12915,
    "Pit of Saron": 10658,
    "Seat of the Triumvirate": 361753,
    "Skyreach": 61209,
    "Windrunner Spire": 12805,
    "Altar of Fangs": 62993,
    "Murder Row": 62813,
    "Den of Nalorakk": 62825,
    "The Blinding Vale": 62859,
    "Voidscar Arena": 62923,
    "Kings' Rest": 61762,
    "Ruby Life Pools": 162521,
    "Temple of Sethraliss": 111877,
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

HEALER_SPECS = frozenset({65, 105, 256, 257, 264, 270, 1468})
REGION_NAMES = {1: "US", 2: "KR", 3: "EU", 4: "TW", 5: "CN"}
