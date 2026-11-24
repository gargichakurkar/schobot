from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ScholarshipSource:
    key: str
    name: str
    listing_url: str
    allowed_hosts: tuple[str, ...]
    enabled: bool
    adapter: str | None


NSP_URL = "https://scholarships.gov.in/All-Scholarships"

SOURCES = {
    "nsp": ScholarshipSource(
        key="nsp",
        name="National Scholarship Portal",
        listing_url=NSP_URL,
        allowed_hosts=("scholarships.gov.in", "www.scholarships.gov.in"),
        enabled=True,
        adapter="nsp",
    ),
    "aicte": ScholarshipSource(
        key="aicte",
        name="AICTE",
        listing_url="https://www.aicte-india.org/",
        allowed_hosts=("aicte-india.org", "www.aicte-india.org"),
        enabled=False,
        adapter=None,
    ),
    "mahadbt": ScholarshipSource(
        key="mahadbt",
        name="Maharashtra MahaDBT",
        listing_url="https://mahadbt.maharashtra.gov.in/",
        allowed_hosts=(
            "mahadbt.maharashtra.gov.in",
            "www.mahadbt.maharashtra.gov.in",
        ),
        enabled=False,
        adapter=None,
    ),
}

ENABLED_SOURCE_KEYS = frozenset(
    source.key for source in SOURCES.values() if source.enabled
)
APPROVED_HOSTS = frozenset(
    host for source in SOURCES.values() for host in source.allowed_hosts
)


def is_approved_https_url(url: str, source_key: str | None = None) -> bool:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return False
    host = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return False
    if source_key is not None:
        source = SOURCES.get(source_key)
        if source is None:
            return False
        allowed_hosts = source.allowed_hosts
    else:
        allowed_hosts = APPROVED_HOSTS
    return host in allowed_hosts


def enabled_sources() -> tuple[ScholarshipSource, ...]:
    return tuple(SOURCES[key] for key in sorted(ENABLED_SOURCE_KEYS))
