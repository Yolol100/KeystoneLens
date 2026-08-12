from __future__ import annotations
import re

RU_REALM_MAP = {
    "соулфлэйер":"soulflayer", "ревущий фьорд":"howling-fjord", "голдрин":"goldrinn",
    "гордунни":"gordunni", "страж смерти":"deathguard", "ткач снов":"dreamweaver",
    "подземье":"deepholm", "седогрив":"greymane", "вечная песня":"eversong",
    "ясеневый лес":"ashenvale", "лазурная стража":"azuregos", "король-лич":"lich-king",
    "черный шрам":"blackscar", "пиратская бухта":"booty-bay", "галакронд":"galakrond",
    "борейская тундра":"borean-tundra", "разувий":"razuvious", "термоштепсель":"termoplug",
}

def split_name_realm(raw: str, default_realm: str = "") -> tuple[str,str]:
    if "-" in raw:
        name, realm = raw.split("-", 1)
        return name.strip(), realm.strip()
    return raw.strip(), default_realm.strip()

def realm_slug(realm: str) -> str:
    cleaned = realm.strip()
    if not cleaned:
        return ""
    compact = re.sub(r"[^\w]", "", cleaned.casefold())
    for key, value in RU_REALM_MAP.items():
        if cleaned.casefold() == key or compact == re.sub(r"[^\w]", "", key.casefold()):
            return value
    s = cleaned.casefold().replace("'", "").replace("’", "")
    s = re.sub(r"[^\w]+", "-", s, flags=re.UNICODE).strip("-")
    return s

