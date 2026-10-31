_COUNTRY_CODES = {
    "usa": "us",
    "united states": "us",
    "united states of america": "us",
    "canada": "ca",
    "uk": "gb",
    "united kingdom": "gb",
    "great britain": "gb",
    "england": "gb",
    "scotland": "gb",
    "wales": "gb",
    "northern ireland": "gb",
    "australia": "au",
    "new zealand": "nz",
    "ireland": "ie",
    "mexico": "mx",
    "germany": "de",
    "france": "fr",
    "spain": "es",
    "italy": "it",
    "netherlands": "nl",
    "belgium": "be",
    "sweden": "se",
    "norway": "no",
    "finland": "fi",
    "denmark": "dk",
    "poland": "pl",
    "russia": "ru",
    "ukraine": "ua",
    "japan": "jp",
    "south africa": "za",
    "brazil": "br",
    "argentina": "ar",
}


def country_code(value: object) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    return _COUNTRY_CODES.get(text, text)
