"""ChronoVault 2.1 — offline baby-name atlas + phonetic shortlist engine.

This is a *cultural suggestion* engine, not a prediction of a real child's
name. It uses a curated, offline name bank (no API keys), then ranks names by
style fit, surname phonetics and deterministic variety.

Every caller must label the result SPECULATIVE. Names and meanings are common
transliterations; meanings vary by language, region and family tradition.
"""
from __future__ import annotations

import hashlib
import re

# culture -> gender -> [(name, meaning, style)]
# style: classic | modern | unique | religious
NAMES: dict[str, dict[str, list[tuple[str, str, str]]]] = {
    "urdu": {
        "boy": [
            ("Muhammad", "praised; praised one", "religious"),
            ("Ahmed", "most praised", "religious"),
            ("Ali", "exalted; noble", "classic"),
            ("Hassan", "handsome; good", "classic"),
            ("Hussain", "beautiful; good", "classic"),
            ("Usman", "baby bustard; steadfast (companion name)", "classic"),
            ("Umar", "flourishing; long-lived", "classic"),
            ("Abdullah", "servant of Allah", "religious"),
            ("Hamza", "lion; strength", "classic"),
            ("Bilal", "freshness; water", "religious"),
            ("Zain", "beauty; grace", "modern"),
            ("Rayyan", "gate of paradise", "modern"),
            ("Ayaan", "gift of God", "modern"),
            ("Ibrahim", "father of many", "religious"),
            ("Yusuf", "God increases", "religious"),
            ("Ismail", "God hears", "religious"),
            ("Musa", "drawn from water", "religious"),
            ("Dawood", "beloved", "religious"),
            ("Sulaiman", "peaceful", "religious"),
            ("Haroon", "mountain of strength", "religious"),
            ("Saad", "good fortune", "classic"),
            ("Fahad", "panther", "classic"),
            ("Danish", "knowledge; wisdom", "modern"),
            ("Adnan", "settler", "classic"),
            ("Tariq", "morning star", "classic"),
            ("Imran", "prosperity", "classic"),
            ("Kamran", "successful", "classic"),
            ("Farhan", "happy", "modern"),
            ("Shahzaib", "prince", "unique"),
            ("Arham", "mercy", "modern"),
            ("Azaan", "call to prayer", "modern"),
            ("Faizan", "grace; bounty", "modern"),
            ("Rizwan", "pleasure; acceptance", "classic"),
            ("Shayan", "worthy; deserving", "modern"),
            ("Sameer", "companion in evening talk", "classic"),
            ("Aamir", "prince; commander", "classic"),
            ("Babar", "lion", "classic"),
            ("Junaid", "young warrior", "classic"),
            ("Kashif", "revealer", "classic"),
            ("Noman", "blessing", "classic"),
            ("Rehan", "fragrant; sweet basil", "modern"),
            ("Talha", "kind; fruitful tree", "classic"),
            ("Zubair", "strong; firm", "classic"),
        ],
        "girl": [
            ("Ayesha", "alive; living", "religious"),
            ("Fatima", "captivating; one who abstains", "religious"),
            ("Khadija", "trustworthy; premature child", "religious"),
            ("Zainab", "fragrant flower", "religious"),
            ("Maryam", "beloved; sea of sorrow", "religious"),
            ("Amina", "trustworthy; peaceful", "religious"),
            ("Sana", "brilliance; praise", "modern"),
            ("Hira", "diamond; cave", "religious"),
            ("Noor", "light", "classic"),
            ("Mahnoor", "light of the moon", "modern"),
            ("Iqra", "read; recite", "religious"),
            ("Anaya", "gift of God; caring", "modern"),
            ("Aleena", "soft; delicate", "modern"),
            ("Hania", "happiness; flowers", "modern"),
            ("Areeba", "wise; intelligent", "modern"),
            ("Eman", "faith", "religious"),
            ("Laiba", "heavenly; beautiful", "modern"),
            ("Rida", "contentment; satisfaction", "religious"),
            ("Saba", "breeze; morning wind", "classic"),
            ("Sadia", "fortunate; happy", "classic"),
            ("Sidra", "lote tree; heavenly tree", "religious"),
            ("Sumaya", "high; elevated", "classic"),
            ("Warda", "rose", "classic"),
            ("Zara", "princess; blossom", "modern"),
            ("Zoya", "alive; life", "modern"),
            ("Alina", "light; noble", "modern"),
            ("Amna", "safe; peaceful", "classic"),
            ("Hafsa", "young lioness", "religious"),
            ("Huma", "bird of paradise", "unique"),
            ("Kiran", "ray of light", "classic"),
            ("Mehwish", "moonlight; beautiful", "classic"),
            ("Nimra", "leopardess; strong", "unique"),
            ("Rabia", "spring; fourth", "classic"),
            ("Saira", "traveler; wandering", "classic"),
            ("Shazia", "fragrant; rare", "classic"),
            ("Uzma", "greatest; supreme", "classic"),
            ("Yusra", "easy; prosperous", "religious"),
            ("Mishal", "torch; light", "unique"),
            ("Maira", "fragrant; swift", "modern"),
            ("Nayab", "rare; precious", "unique"),
        ],
    },
    "arabic": {
        "boy": [
            ("Adam", "man; earth", "religious"),
            ("Omar", "flourishing", "classic"),
            ("Sami", "elevated; sublime", "classic"),
            ("Karim", "generous; noble", "classic"),
            ("Nabil", "noble; intelligent", "classic"),
            ("Rashid", "guided; right-minded", "classic"),
            ("Salim", "safe; sound", "classic"),
            ("Tamer", "date palm; wealthy", "unique"),
            ("Yasin", "heart of the Quran", "religious"),
            ("Zaid", "abundance; growth", "modern"),
            ("Fadi", "redeemer", "unique"),
            ("Hadi", "guide", "religious"),
            ("Jamil", "beautiful; handsome", "classic"),
            ("Khalid", "eternal; immortal", "classic"),
            ("Malik", "king; owner", "classic"),
            ("Nasser", "helper; victorious", "classic"),
            ("Rami", "archer", "modern"),
            ("Tariq", "morning star", "classic"),
        ],
        "girl": [
            ("Layla", "night; dark beauty", "classic"),
            ("Lina", "tender; palm tree", "modern"),
            ("Maya", "water; illusion", "modern"),
            ("Nour", "light", "religious"),
            ("Salma", "safe; peaceful", "classic"),
            ("Yasmin", "jasmine flower", "classic"),
            ("Rania", "gazing; queenly", "modern"),
            ("Dana", "pearl; generous", "modern"),
            ("Farah", "joy; happiness", "classic"),
            ("Hala", "halo; moon", "unique"),
            ("Jana", "garden; paradise", "modern"),
            ("Malak", "angel", "religious"),
            ("Reem", "gazelle; white antelope", "classic"),
            ("Rana", "elegant; gaze", "classic"),
            ("Sara", "princess; pure", "classic"),
            ("Tala", "dew; young palm", "unique"),
            ("Yara", "small butterfly; friend", "modern"),
            ("Alya", "sky; loftiness", "modern"),
        ],
    },
    "english": {
        "boy": [
            ("Oliver", "olive tree", "classic"),
            ("Noah", "rest; comfort", "classic"),
            ("Liam", "strong-willed warrior", "modern"),
            ("Ethan", "strong; firm", "classic"),
            ("Lucas", "bringer of light", "classic"),
            ("Mason", "stone worker", "modern"),
            ("Logan", "little hollow", "modern"),
            ("James", "supplanter", "classic"),
            ("Benjamin", "son of the right hand", "classic"),
            ("Henry", "ruler of the home", "classic"),
            ("Alexander", "defender of the people", "classic"),
            ("Daniel", "God is my judge", "classic"),
            ("William", "resolute protector", "classic"),
            ("Michael", "who is like God", "classic"),
            ("Samuel", "asked of God", "classic"),
            ("Joseph", "God will increase", "classic"),
            ("David", "beloved", "classic"),
            ("Thomas", "twin", "classic"),
            ("Charles", "free man", "classic"),
            ("Arthur", "bear; noble", "classic"),
            ("Theodore", "gift of God", "modern"),
            ("Jack", "God is gracious", "classic"),
            ("Leo", "lion", "modern"),
            ("Oscar", "deer friend; spear of God", "modern"),
            ("Harry", "home ruler", "classic"),
            ("Alfie", "wise counselor", "modern"),
            ("Freddie", "peaceful ruler", "modern"),
            ("Archie", "genuine; bold", "modern"),
        ],
        "girl": [
            ("Olivia", "olive tree", "classic"),
            ("Emma", "whole; universal", "classic"),
            ("Amelia", "work; industrious", "classic"),
            ("Sophia", "wisdom", "classic"),
            ("Isabella", "devoted to God", "classic"),
            ("Mia", "mine; beloved", "modern"),
            ("Charlotte", "free; petite", "classic"),
            ("Ava", "life; bird", "modern"),
            ("Grace", "grace; favor", "classic"),
            ("Lily", "lily flower", "classic"),
            ("Chloe", "green shoot; blooming", "modern"),
            ("Ella", "she; light", "modern"),
            ("Emily", "industrious; rival", "classic"),
            ("Alice", "noble", "classic"),
            ("Florence", "flourishing; prosperous", "unique"),
            ("Freya", "noble woman; goddess", "modern"),
            ("Poppy", "red flower", "modern"),
            ("Rosie", "rose", "classic"),
            ("Ruby", "red gemstone", "modern"),
            ("Evie", "life; living", "modern"),
            ("Isabelle", "devoted to God", "classic"),
            ("Ivy", "ivy plant", "unique"),
            ("Matilda", "mighty in battle", "unique"),
            ("Willow", "willow tree", "unique"),
        ],
    },
    "turkish": {
        "boy": [
            ("Emir", "prince; commander", "classic"),
            ("Yusuf", "God increases", "religious"),
            ("Eymen", "blessed; right-handed", "modern"),
            ("Kerem", "generosity; nobility", "classic"),
            ("Aras", "rivers; calm", "unique"),
            ("Ege", "Aegean; guardian", "modern"),
            ("Alparslan", "heroic lion", "unique"),
            ("Metehan", "great khan", "unique"),
            ("Kaan", "king; ruler", "classic"),
            ("Baran", "rain", "modern"),
            ("Berk", "strong; solid", "classic"),
            ("Cem", "gathering; ruler", "classic"),
            ("Deniz", "sea", "modern"),
            ("Efe", "brave; older brother", "classic"),
            ("Furkan", "criterion; discernment", "religious"),
            ("Mert", "brave; honest", "classic"),
            ("Onur", "honor", "classic"),
            ("Tolga", "helmet; strong", "unique"),
        ],
        "girl": [
            ("Zeynep", "precious gem", "classic"),
            ("Elif", "slender; first letter", "classic"),
            ("Defne", "laurel tree", "modern"),
            ("Ada", "island; noble", "modern"),
            ("Azra", "virgin; pure", "religious"),
            ("Eylul", "September; autumn", "modern"),
            ("Zehra", "blossom; radiant", "religious"),
            ("Nehir", "river", "modern"),
            ("Duru", "clear; pure", "unique"),
            ("Ela", "hazel; light", "modern"),
            ("Asli", "genuine; original", "classic"),
            ("Aylin", "moon halo", "classic"),
            ("Busra", "good news", "religious"),
            ("Ceylin", "gazelle; graceful", "modern"),
            ("Derin", "deep", "unique"),
            ("Ece", "queen; beautiful", "classic"),
            ("Gamze", "dimple", "classic"),
            ("Irem", "garden of paradise", "religious"),
            ("Lara", "cheerful; laurel", "modern"),
            ("Melis", "honey; sweet", "unique"),
            ("Nisa", "woman; companion", "religious"),
            ("Selin", "moon; calm water", "classic"),
            ("Tuana", "first light; paradise", "unique"),
        ],
    },
    "persian": {
        "boy": [
            ("Arman", "ideal; aspiration", "modern"),
            ("Aryan", "noble; Indo-Iranian", "classic"),
            ("Babak", "little father", "classic"),
            ("Cyrus", "sun; throne", "classic"),
            ("Dariush", "possessing goodness", "classic"),
            ("Farid", "unique; precious", "classic"),
            ("Kaveh", "hero; blacksmith", "unique"),
            ("Khosrow", "good ruler", "unique"),
            ("Mehrdad", "gift of the sun", "classic"),
            ("Omid", "hope", "modern"),
            ("Parsa", "pure; Persian", "modern"),
            ("Reza", "contentment; approval", "religious"),
            ("Ramin", "joyful; happy", "classic"),
            ("Shahin", "royal falcon", "unique"),
            ("Sohrab", "illustrious; shining", "unique"),
            ("Vahid", "unique; one", "classic"),
            ("Yazdan", "God; divine", "religious"),
            ("Zia", "light; splendor", "classic"),
        ],
        "girl": [
            ("Anahita", "goddess of water", "unique"),
            ("Arezoo", "wish; desire", "classic"),
            ("Azadeh", "free; noble", "unique"),
            ("Bahar", "spring", "classic"),
            ("Darya", "sea", "classic"),
            ("Elham", "inspiration", "religious"),
            ("Farah", "joy", "classic"),
            ("Golnar", "pomegranate flower", "unique"),
            ("Laleh", "tulip", "classic"),
            ("Leila", "night", "classic"),
            ("Mahsa", "moon-like", "modern"),
            ("Neda", "call; voice", "classic"),
            ("Parisa", "fairy-like; beautiful", "classic"),
            ("Roxana", "dawn; bright", "unique"),
            ("Sahar", "dawn", "classic"),
            ("Shirin", "sweet", "classic"),
            ("Yasmin", "jasmine", "classic"),
            ("Zahra", "blossom; radiant", "religious"),
        ],
    },
    "hindi": {
        "boy": [
            ("Aarav", "peaceful; melodious", "modern"),
            ("Vivaan", "full of life", "modern"),
            ("Aditya", "sun; first light", "classic"),
            ("Arjun", "bright; white", "classic"),
            ("Reyansh", "ray of light", "modern"),
            ("Krishna", "dark; attractive", "religious"),
            ("Ishaan", "sun; protector", "modern"),
            ("Shivansh", "part of Shiva", "religious"),
            ("Rudra", "roarer; Shiva", "religious"),
            ("Kabir", "great; poet-saint", "classic"),
            ("Rohan", "ascending; healing", "classic"),
            ("Veer", "brave; warrior", "modern"),
            ("Dhruv", "pole star; steadfast", "classic"),
            ("Yash", "fame; glory", "classic"),
            ("Om", "sacred syllable", "religious"),
            ("Nikhil", "whole; complete", "classic"),
            ("Rahul", "efficient; conqueror", "classic"),
            ("Vikram", "valor; stride", "classic"),
            ("Suresh", "ruler of gods", "classic"),
            ("Ravi", "sun", "classic"),
        ],
        "girl": [
            ("Aadhya", "first power; goddess", "modern"),
            ("Saanvi", "goddess Lakshmi", "modern"),
            ("Ananya", "unique; matchless", "modern"),
            ("Diya", "lamp; light", "classic"),
            ("Pari", "fairy; angel", "modern"),
            ("Ira", "earth; muse", "unique"),
            ("Myra", "beloved; sweet", "modern"),
            ("Sara", "essence; princess", "classic"),
            ("Aanya", "grace; inexhaustible", "modern"),
            ("Navya", "new; worthy of praise", "modern"),
            ("Kiara", "bright; clear", "modern"),
            ("Riya", "singer; graceful", "classic"),
            ("Pooja", "worship", "classic"),
            ("Priya", "beloved; dear", "classic"),
            ("Neha", "love; affection", "classic"),
            ("Kavya", "poetry", "classic"),
            ("Meera", "prosperous; saint-poet", "religious"),
            ("Nisha", "night", "classic"),
            ("Radha", "success; beloved of Krishna", "religious"),
            ("Sita", "furrow; goddess", "religious"),
        ],
    },
    "sindhi": {
        "boy": [
            ("Sarmad", "eternal; steadfast", "classic"),
            ("Sohail", "gentle; star", "classic"),
            ("Naveed", "good news", "classic"),
            ("Asad", "lion", "classic"),
            ("Faisal", "decisive; judge", "classic"),
            ("Waqar", "dignity; majesty", "classic"),
            ("Zohaib", "golden; shining", "unique"),
            ("Shakil", "handsome", "classic"),
            ("Mumtaz", "distinguished; chosen", "classic"),
            ("Latif", "gentle; kind", "classic"),
            ("Ayaz", "cool breeze; servant", "unique"),
            ("Junaid", "young warrior", "classic"),
        ],
        "girl": [
            ("Sanam", "beloved; idol", "classic"),
            ("Saima", "fasting; blessed", "religious"),
            ("Nazia", "pride; fresh", "classic"),
            ("Shabana", "young; morning dew", "classic"),
            ("Rukhsana", "charming; bright", "classic"),
            ("Farzana", "wise; intelligent", "classic"),
            ("Rubina", "ruby; precious", "classic"),
            ("Nasreen", "wild rose", "classic"),
            ("Parveen", "cluster of stars", "classic"),
            ("Gulzar", "rose garden", "unique"),
            ("Marvi", "legendary Sindhi heroine", "unique"),
            ("Sassui", "legendary Sindhi heroine", "unique"),
            ("Hina", "henna; fragrance", "modern"),
        ],
    },
    "punjabi": {
        "boy": [
            ("Gurpreet", "love of the guru", "religious"),
            ("Harjit", "victory of God", "religious"),
            ("Manpreet", "love of the mind", "classic"),
            ("Jaspreet", "love of praise", "classic"),
            ("Navdeep", "new light", "modern"),
            ("Ranjit", "victorious in battle", "classic"),
            ("Sukhwinder", "comfort of God", "religious"),
            ("Balwinder", "strength of God", "classic"),
            ("Amrit", "immortal nectar", "religious"),
            ("Arjan", "noble; warrior", "classic"),
            ("Fateh", "victory", "modern"),
            ("Jaskaran", "service to God", "religious"),
        ],
        "girl": [
            ("Simran", "meditation; remembrance", "religious"),
            ("Harleen", "absorbed in God", "religious"),
            ("Jasleen", "absorbed in praise", "classic"),
            ("Navneet", "new moral", "modern"),
            ("Rupinder", "beauty of the lord", "classic"),
            ("Manjit", "victory of the mind", "classic"),
            ("Sukhjit", "victory of peace", "classic"),
            ("Amandeep", "lamp of peace", "classic"),
            ("Gurleen", "absorbed in the guru", "religious"),
            ("Kiranjit", "ray of light", "classic"),
            ("Preet", "love", "modern"),
            ("Mehak", "fragrance", "modern"),
        ],
    },
}

CULTURE_LABEL = {
    "urdu": "Urdu / Muslim",
    "arabic": "Arabic",
    "english": "English",
    "turkish": "Turkish",
    "persian": "Persian",
    "hindi": "Hindi / Sanskrit",
    "sindhi": "Sindhi",
    "punjabi": "Punjabi",
    "mix": "Mixed",
}

CULTURE_ALIASES = {
    "urdu": "urdu", "muslim": "urdu", "islam": "urdu", "islamic": "urdu",
    "pakistani": "urdu", "pakistan": "urdu", "roman urdu": "urdu",
    "arab": "arabic", "arabic": "arabic",
    "english": "english", "western": "english", "eng": "english",
    "turk": "turkish", "turkish": "turkish", "turkey": "turkish",
    "persian": "persian", "farsi": "persian", "iranian": "persian",
    "hindi": "hindi", "indian": "hindi", "sanskrit": "hindi",
    "sindhi": "sindhi", "sindh": "sindhi",
    "punjabi": "punjabi", "sikh": "punjabi",
    "mix": "mix", "mixed": "mix", "any": "mix", "koi bhi": "mix",
}

STYLES = ("classic", "modern", "unique", "religious", "any")

STYLE_ALIASES = {
    "classic": "classic", "traditional": "classic", "purana": "classic",
    "purani": "classic", "old": "classic", "evergreen": "classic",
    "modern": "modern", "new": "modern", "naya": "modern", "trendy": "modern",
    "unique": "unique", "rare": "unique", "alaag": "unique", "different": "unique",
    "religious": "religious", "islamic": "religious", "deeni": "religious",
    "deen": "religious", "quranic": "religious",
    "any": "any", "koi bhi": "any", "sab": "any", "surprise": "any",
}

GENDER_ALIASES = {
    "boy": "boy", "ladka": "boy", "beta": "boy", "male": "boy", "mard": "boy",
    "girl": "girl", "ladki": "girl", "beti": "girl", "female": "girl",
    "any": "any", "surprise": "any", "dono": "any", "koi bhi": "any",
    "pata nahi": "any",
}


def normalize_culture(text: str) -> str:
    t = (text or "").strip().lower()
    for key, value in CULTURE_ALIASES.items():
        if key == t or re.search(r"\b" + re.escape(key) + r"\b", t):
            return value
    return "urdu"


def normalize_gender(text: str) -> str:
    t = (text or "").strip().lower()
    for key, value in GENDER_ALIASES.items():
        if key == t or re.search(r"\b" + re.escape(key) + r"\b", t):
            return value
    return "any"


def normalize_style(text: str) -> str:
    t = (text or "").strip().lower()
    for key, value in STYLE_ALIASES.items():
        if key == t or re.search(r"\b" + re.escape(key) + r"\b", t):
            return value
    return "any"


def _seed(*parts: str) -> int:
    raw = "|".join(parts).encode("utf-8")
    return int(hashlib.sha1(raw).hexdigest()[:8], 16)


def _pool(culture: str, gender: str) -> list[tuple[str, str, str, str]]:
    cultures = list(NAMES) if culture == "mix" else [culture]
    out = []
    for c in cultures:
        if c not in NAMES:
            continue
        for g in ("boy", "girl"):
            if gender != "any" and g != gender:
                continue
            for (name, meaning, style) in NAMES[c][g]:
                out.append((name, meaning, style, g))
    return out


def _score(name: str, style: str, surname: str, wanted_style: str,
           *salt: str) -> tuple[float, list[str]]:
    score = 0.5
    reasons = []
    if wanted_style and wanted_style != "any":
        if style == wanted_style:
            score += 0.22
            reasons.append(f"{wanted_style} style")
        else:
            score -= 0.06
    if surname:
        if name[0].lower() == surname[0].lower():
            score += 0.05
            reasons.append("surname ke saath alliteration")
        if abs(len(name) - len(surname)) <= 2:
            score += 0.04
            reasons.append("surname ke saath balanced length")
        if name[-1].lower() == surname[0].lower():
            score -= 0.04
    score += (_seed(name, surname or "", wanted_style or "", *salt) % 1000) / 10000.0
    return score, reasons


def suggest(gender: str, surname: str = "", culture: str = "urdu",
            style: str = "any", count: int = 5) -> dict:
    """Return a deterministic, ranked, culturally-labelled shortlist."""
    gender = normalize_gender(gender)
    culture = normalize_culture(culture)
    style = normalize_style(style)
    surname = re.sub(r"[^A-Za-z' -]", "", (surname or "").strip())
    surname = " ".join(w.capitalize() for w in surname.split())[:40]

    pool = _pool(culture, gender)
    scored = []
    for (name, meaning, style_tag, g) in pool:
        score, reasons = _score(name, style_tag, surname, style, culture, g)
        scored.append((score, name, meaning, style_tag, g, reasons))
    scored.sort(key=lambda x: (-x[0], x[1]))

    picks = []
    initials: dict[str, int] = {}
    for score, name, meaning, style_tag, g, reasons in scored:
        if initials.get(name[0].upper(), 0) >= 2:
            continue
        initials[name[0].upper()] = initials.get(name[0].upper(), 0) + 1
        picks.append({
            "name": name,
            "full_name": f"{name} {surname}".strip(),
            "meaning": meaning,
            "origin": CULTURE_LABEL.get(culture, culture),
            "style": style_tag,
            "gender": g,
            "score": round(min(0.95, score), 3),
            "why": reasons + [f"matlab: {meaning}"],
        })
        if len(picks) >= max(1, int(count)):
            break

    year = 2026 + (_seed(surname or "khan", culture, style) % 4)
    return {
        "engine": "BABY-NAME-ATLAS v1 (offline cultural + phonetic model)",
        "gender": gender,
        "surname": surname,
        "culture": culture,
        "culture_label": CULTURE_LABEL.get(culture, culture),
        "style": style,
        "pool_size": len(pool),
        "names": picks,
        "snapshot_year": year,
        "note": ("Yeh cultural/phonetic shortlist hai — bachay ka asli naam "
                 "aap aur aapki family tay karengi. Koi guaranteed prediction "
                 "nahi. Meanings transliteration ke hisaab se hain aur "
                 "region/family tradition me badal sakte hain."),
    }


def to_text(result: dict) -> str:
    names = result.get("names") or []
    if not names:
        return ("Is culture/style ke liye mere paas naam nahi mile. Culture "
                "ya style badal kar dobara poochein.")
    lines = [
        f"{result['culture_label']} • {result['gender']} • "
        f"style: {result['style']} • {result['pool_size']} naam ki pool se "
        f"shortlist:",
    ]
    for i, n in enumerate(names, 1):
        lines.append(f"{i}. {n['full_name']} — “{n['meaning']}” "
                     f"({n['origin']}, {n['style']})")
        if n.get("why"):
            lines.append("   " + " · ".join(n["why"][:3]))
    lines.append(
        f"Simulated future snapshot ({result['snapshot_year']}): "
        f"{names[0]['full_name']} — yeh sirf ek imaginative snapshot hai, "
        f"koi prediction nahi.")
    lines.append(result["note"])
    return "\n".join(lines)
