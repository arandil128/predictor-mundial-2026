"""Banderas de selecciones: código FIFA (3 letras) -> ISO 3166-1 alpha-2 -> emoji.

Se usa en los mensajes de WhatsApp, donde los emojis de bandera SÍ se renderizan.
En el frontend la misma tabla vive en static/app.js, pero ahí se usan imágenes de
flagcdn porque Windows no dibuja los emojis de bandera. Si editás una, actualizá
las dos.
"""
from __future__ import annotations

# Código FIFA -> ISO 3166-1 alpha-2 (Inglaterra/Escocia/Gales usan subdivisiones gb-*).
FIFA_TO_ISO2 = {
    "ARG": "ar", "FRA": "fr", "ESP": "es", "ENG": "gb-eng", "BRA": "br", "POR": "pt",
    "NED": "nl", "BEL": "be", "ITA": "it", "GER": "de", "CRO": "hr", "URU": "uy",
    "COL": "co", "MAR": "ma", "SUI": "ch", "DEN": "dk", "MEX": "mx", "USA": "us",
    "SEN": "sn", "JPN": "jp", "ECU": "ec", "AUT": "at", "UKR": "ua", "IRN": "ir",
    "KOR": "kr", "SWE": "se", "SRB": "rs", "POL": "pl", "WAL": "gb-wls", "AUS": "au",
    "PER": "pe", "HUN": "hu", "TUR": "tr", "NGA": "ng", "NOR": "no", "EGY": "eg",
    "CZE": "cz", "SCO": "gb-sct", "CHI": "cl", "ALG": "dz", "GRE": "gr", "CMR": "cm",
    "TUN": "tn", "CAN": "ca", "CIV": "ci", "ROU": "ro", "CRC": "cr", "PAR": "py",
    "GHA": "gh", "KSA": "sa", "SVK": "sk", "SVN": "si", "MLI": "ml", "QAT": "qa",
    "VEN": "ve", "IRQ": "iq", "IRL": "ie", "BIH": "ba", "FIN": "fi", "PAN": "pa",
    "RSA": "za", "BFA": "bf", "ALB": "al", "MKD": "mk", "CPV": "cv", "GEO": "ge",
    "UAE": "ae", "JAM": "jm", "UZB": "uz", "COD": "cd", "JOR": "jo", "HON": "hn",
    "OMA": "om", "BOL": "bo", "NZL": "nz", "CUW": "cw", "HAI": "ht",
}


def _regional(letter: str) -> str:
    """Letra a..z -> símbolo indicador regional (los que forman la bandera emoji)."""
    return chr(0x1F1E6 + ord(letter) - ord("a"))


def _subdivision_flag(sub: str) -> str:
    """Bandera de subdivisión (Inglaterra/Escocia/Gales) por secuencia de tags."""
    return "\U0001F3F4" + "".join(chr(0xE0000 + ord(c)) for c in sub) + "\U000E007F"


def emoji_flag(fifa_code: str | None) -> str:
    """Emoji de bandera para un código FIFA (cadena vacía si no se conoce)."""
    iso = FIFA_TO_ISO2.get((fifa_code or "").upper())
    if not iso:
        return ""
    if "-" in iso:  # gb-eng / gb-sct / gb-wls
        return _subdivision_flag(iso.replace("-", ""))
    return _regional(iso[0]) + _regional(iso[1])
