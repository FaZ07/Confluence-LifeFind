"""
LifeFind — authority handoff.

LifeFind only aggregates *public* signal; it never replaces the authorities.
This module surfaces the real official channels for the case's region so a
searcher's next click is "report to the people who can act". Numbers/links are
seeds — always verify locally; emergencies go to the local emergency number.
"""
from __future__ import annotations

# Region detection by keyword in the last-seen location (cheap + offline).
_COUNTRY_KEYWORDS = {
    "IN": ["india", "chennai", "tamil", "kerala", "mumbai", "delhi", "bengaluru", "bangalore",
           "hyderabad", "kolkata", "pune", "andhra", "karnataka", "pondicherry", "puducherry"],
    "US": ["usa", "united states", " u.s", "america", "new york", "california", "texas",
           "florida", "chicago", "los angeles", "boston", "seattle"],
    "GB": ["uk", "united kingdom", "england", "london", "scotland", "wales", "manchester"],
    "AU": ["australia", "sydney", "melbourne", "brisbane", "perth", "adelaide"],
    "CA": ["canada", "toronto", "vancouver", "montreal", "ottawa"],
}

_CHANNELS: dict[str, list[dict]] = {
    "IN": [
        {"name": "Police", "scope": "Immediate danger", "phone": "100", "url": ""},
        {"name": "Childline India", "scope": "Missing / at-risk child", "phone": "1098",
         "url": "https://www.childlineindia.org"},
        {"name": "TrackChild / Khoya-Paya", "scope": "National missing-child portal", "phone": "",
         "url": "https://trackthemissing.gov.in"},
        {"name": "Women Helpline", "scope": "Missing woman / distress", "phone": "181", "url": ""},
    ],
    "US": [
        {"name": "Emergency (911)", "scope": "Immediate danger", "phone": "911", "url": ""},
        {"name": "NCMEC (missing child)", "scope": "National Center for Missing & Exploited Children",
         "phone": "1-800-843-5678", "url": "https://www.missingkids.org"},
        {"name": "NamUs", "scope": "National Missing & Unidentified Persons System", "phone": "",
         "url": "https://www.namus.gov"},
    ],
    "GB": [
        {"name": "Emergency (999)", "scope": "Immediate danger", "phone": "999", "url": ""},
        {"name": "Missing People", "scope": "UK charity, 24/7 free + confidential", "phone": "116 000",
         "url": "https://www.missingpeople.org.uk"},
    ],
    "AU": [
        {"name": "Emergency (000)", "scope": "Immediate danger", "phone": "000", "url": ""},
        {"name": "Australian Federal Police — Missing Persons", "scope": "National coordination",
         "phone": "", "url": "https://www.missingpersons.gov.au"},
    ],
    "CA": [
        {"name": "Emergency (911)", "scope": "Immediate danger", "phone": "911", "url": ""},
        {"name": "MissingKids.ca", "scope": "Canada's missing children resource", "phone": "1-866-543-8477",
         "url": "https://missingkids.ca"},
    ],
}

_GLOBAL = [
    {"name": "INTERPOL — Yellow Notices", "scope": "Cross-border missing persons", "phone": "",
     "url": "https://www.interpol.int/How-we-work/Notices/Yellow-Notices"},
    {"name": "ICMEC", "scope": "International missing & exploited children", "phone": "",
     "url": "https://www.icmec.org"},
]


def detect_country(location: str) -> str:
    low = (location or "").lower()
    for code, kws in _COUNTRY_KEYWORDS.items():
        if any(k in low for k in kws):
            return code
    return "global"


def for_location(location: str) -> dict:
    """Return the official channels relevant to a case location."""
    code = detect_country(location)
    regional = _CHANNELS.get(code, [])
    return {
        "country": code,
        "note": "LifeFind aggregates public signal only. Report to and verify with these "
                "official channels — in an emergency call your local emergency number.",
        "channels": regional + _GLOBAL,
    }
