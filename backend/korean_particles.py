import re


_FINAL_CONSONANT_OVERRIDES = {
    "S-Oil": True,
    "S-OIL": True,
}


def has_final_consonant(text: str) -> bool:
    value = str(text or "").strip()
    if value in _FINAL_CONSONANT_OVERRIDES:
        return _FINAL_CONSONANT_OVERRIDES[value]

    for character in reversed(value):
        code = ord(character)
        if 0xAC00 <= code <= 0xD7A3:
            return (code - 0xAC00) % 28 != 0
    return False


def with_particle(text: str, consonant_particle: str, vowel_particle: str) -> str:
    particle = consonant_particle if has_final_consonant(text) else vowel_particle
    return f"{text}{particle}"


def normalize_company_pair_particles(question: str) -> str:
    """Normalize the first 과/와 in company-pair questions such as 'A와 B의 ...'."""

    def replace(match: re.Match) -> str:
        company = match.group("company")
        return with_particle(company, "과", "와")

    return re.sub(
        r"(?P<company>[A-Za-z0-9가-힣.&()+-]+)(?:과|와)(?=\s+\S+의\s)",
        replace,
        str(question or ""),
        count=1,
    )
