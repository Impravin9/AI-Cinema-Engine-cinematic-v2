"""Conservative licence allow-list for downloadable documentary still images."""
import re


def lic_ok(license_name: str | None) -> bool:
    """Allow public domain, CC0 and CC BY; exclude NC, ND, SA and ambiguous labels."""
    value = re.sub(r"\s+", " ", (license_name or "").strip().lower())
    if value in {"public domain", "public domain mark", "pdm", "cc0", "cc0 1.0"}:
        return True
    return re.fullmatch(r"cc[- ]by(?:[- ]?\d+(?:\.\d+)?)?", value) is not None
