from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from urllib.error import HTTPError, URLError

from app.core.database import Base
from app.models import (
    Scholarship,
    ScholarshipIngestionEvent,
    ScholarshipIngestionRun,
    ScholarshipIngestionSource,
    ScholarshipIngestionState,
)
from app.seed.import_scholarships import DATA_DIRECTORY, DUAL_FILENAME
from app.services.scholarship_fetcher import nsp_fetcher
from app.services.scholarship_fetcher.source_config import is_approved_https_url


@pytest.fixture(autouse=True)
def clear_robots_cache():
    nsp_fetcher._ROBOTS_CACHE.clear()
    yield
    nsp_fetcher._ROBOTS_CACHE.clear()


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def make_scheme(name: str, provider: str = "NSP Provider", **overrides):
    scheme = {
        "scholarship_name": name,
        "provider": provider,
        "official_link": "https://scholarships.gov.in/All-Scholarships",
        "scheme_info_link": "https://scholarships.gov.in/guideline.pdf",
        "application_deadline": "15-03-2027",
        "benefits": "Annual grant",
        "eligibility_details": "Official eligibility conditions",
    }
    scheme.update(overrides)
    return scheme


def test_extract_schemes_finds_official_links_deadline_and_distinct_providers():
    html = """
    <div class="accordion-item">
      <div class="accordion-header">Ministry One</div>
      <div class="accordion-body">
        <div class="row mb-4">
          <div>Annual Award (Merit Based Scheme)
            Student Application Open from: 01-01-2027
            Student Application Open till: 15-03-2027
          </div>
          <a href="/apply">Apply Now</a>
          <a href="/guideline.pdf">Specification</a>
          <a href="/faq">FAQ</a>
        </div>
      </div>
    </div>
    <div class="accordion-item">
      <div class="accordion-header">Ministry Two</div>
      <div class="accordion-body">
        <div class="row mb-4">
          <div>Annual Award (Merit Based Scheme) Student Application Closed on: 16/03/2027</div>
        </div>
      </div>
    </div>
    """

    schemes = nsp_fetcher.extract_schemes(html)

    assert len(schemes) == 2
    first = schemes[0]
    assert first["scholarship_name"] == "Annual Award"
    assert first["provider"] == "Ministry One"
    assert first["official_link"] == "https://scholarships.gov.in/apply"
    assert first["scheme_info_link"] == "https://scholarships.gov.in/guideline.pdf"
    assert first["faq_link"] == "https://scholarships.gov.in/faq"
    assert first["application_start_date"] == "01-01-2027"
    assert first["application_start_evidence"] == (
        "Student Application Open from: 01-01-2027"
    )
    assert schemes[1]["provider"] == "Ministry Two"


def test_extract_schemes_ignores_placeholder_guideline_url():
    html = """
    <div class="accordion-item">
      <div class="accordion-header">Ministry One</div>
      <div class="accordion-body"><div class="row mb-4">
        <div>Annual Award (Merit Based Scheme)</div>
        <a href="null">Specification</a>
      </div></div>
    </div>
    """

    schemes = nsp_fetcher.extract_schemes(html)

    assert schemes[0]["scheme_info_link"] is None


def test_dataset_contract_matches_the_existing_autosaved_csv():
    with (DATA_DIRECTORY / DUAL_FILENAME).open(
        encoding="cp1252",
        newline="",
    ) as source:
        import csv

        reader = csv.DictReader(source)
        assert tuple(reader.fieldnames or ()) == nsp_fetcher.DATASET_COLUMNS


def test_source_allowlist_requires_approved_https_hosts():
    assert is_approved_https_url(nsp_fetcher.NSP_URL)
    assert not is_approved_https_url("http://scholarships.gov.in/")
    assert not is_approved_https_url("https://scholarships.gov.in.example.com/")
    assert not is_approved_https_url("https://unrelated.gov.in/")
    assert is_approved_https_url("https://www.aicte-india.org/")
    assert not nsp_fetcher._is_allowed_official_url(
        "https://www.aicte-india.org/"
    )
    assert not nsp_fetcher._is_allowed_official_url(
        "https://mahadbt.maharashtra.gov.in/"
    )


def test_redirect_handler_rejects_unapproved_hosts_before_following():
    request = nsp_fetcher.Request(nsp_fetcher.NSP_URL)

    with pytest.raises(ValueError, match="outside approved HTTPS domains"):
        nsp_fetcher._AllowlistedRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://unrelated.gov.in/document.pdf",
        )


@pytest.mark.parametrize(
    "target",
    [
        "https://www.aicte-india.org/scholarships",
        "https://mahadbt.maharashtra.gov.in/schemes",
    ],
)
def test_nsp_redirect_handler_rejects_disabled_source_hosts(target):
    request = nsp_fetcher.Request(nsp_fetcher.NSP_URL)

    with pytest.raises(ValueError, match="outside approved HTTPS domains"):
        nsp_fetcher._AllowlistedRedirectHandler("nsp").redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            target,
        )


def test_nsp_dataset_validation_rejects_disabled_source_hosts():
    fields = {column: None for column in nsp_fetcher.DATASET_COLUMNS}
    fields.update(
        {
            "scholarship_name": "Example Award",
            "official_portal_link": "https://www.aicte-india.org/scholarships",
        }
    )

    valid, error = nsp_fetcher._validate_dataset_fields(fields, source_key="nsp")

    assert not valid
    assert error == (
        "official_portal_link is outside the approved HTTPS source domains."
    )


def test_fetch_resource_obeys_robots_disallow_rule(monkeypatch):
    calls = []

    class Response:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return (
                b"User-agent: ScholarMateScholarshipFetcher\n"
                b"Disallow: /All-Scholarships"
            )

    def fake_urlopen(request, **kwargs):
        calls.append(request.full_url)
        return Response()

    monkeypatch.setattr(nsp_fetcher, "urlopen", fake_urlopen)

    with pytest.raises(PermissionError, match="Robots policy disallows"):
        nsp_fetcher._fetch_resource_details(nsp_fetcher.NSP_URL, retries=1)

    assert calls == ["https://scholarships.gov.in/robots.txt"]


def test_missing_robots_file_allows_fetch_but_does_not_skip_https_allowlist(
    monkeypatch,
):
    calls = []

    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b"official page"

        def geturl(self):
            return nsp_fetcher.NSP_URL

    def fake_urlopen(request, **kwargs):
        calls.append(request.full_url)
        if request.full_url.endswith("/robots.txt"):
            raise HTTPError(request.full_url, 404, "Not Found", None, None)
        return Response()

    monkeypatch.setattr(nsp_fetcher, "urlopen", fake_urlopen)
    content, content_type, final_url, _, _ = nsp_fetcher._fetch_resource_details(
        nsp_fetcher.NSP_URL,
        retries=1,
    )

    assert content == b"official page"
    assert content_type == "text/html"
    assert final_url == nsp_fetcher.NSP_URL
    assert calls == [
        "https://scholarships.gov.in/robots.txt",
        nsp_fetcher.NSP_URL,
    ]


def test_deadline_parser_uses_student_application_label_only():
    html = """
    <div class="accordion-item">
      <div class="accordion-header">Ministry One</div>
      <div class="accordion-body"><div class="row mb-4">
        <div>Annual Award (Merit Based Scheme)
          Institute Verification Open till: 20-12-2026
          Student Application Open till: 15-03-2027
        </div>
      </div></div>
    </div>
    """

    scheme = nsp_fetcher.extract_schemes(html)[0]

    assert scheme["application_deadline"] == "15-03-2027"
    assert scheme["deadline_evidence"] == "Student Application Open till: 15-03-2027"
    assert scheme["application_status"] in {"open", "closed"}


@pytest.mark.parametrize(
    "guideline_url",
    [
        None,
        "",
        "null",
        "none",
        "not_available.pdf",
        "https://scholarships.gov.in/null",
    ],
)
def test_enrich_guidelines_skips_placeholder_urls(guideline_url, monkeypatch, caplog):
    def fail_if_downloaded(_):
        pytest.fail("placeholder guideline URL must not be downloaded")

    monkeypatch.setattr(nsp_fetcher, "fetch_guidelines", fail_if_downloaded)
    scheme = make_scheme(
        "Unavailable Guidelines Award",
        scheme_info_link=guideline_url,
        benefits="Already extracted benefit",
    )

    nsp_fetcher._enrich_guidelines([scheme])

    assert scheme["benefits"] == "Already extracted benefit"
    assert "Unavailable Guidelines Award" in caplog.text


def test_enrich_guidelines_continues_after_404_and_timeout(monkeypatch, caplog):
    attempts = {}

    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b"<h2>Benefits:</h2><p>New official grant</p>"

        def geturl(self):
            return self.url

    def fake_urlopen(request, **kwargs):
        url = request.full_url
        attempts[url] = attempts.get(url, 0) + 1
        if "404.pdf" in url:
            raise HTTPError(url, 404, "Not Found", None, None)
        if "timeout.pdf" in url:
            raise TimeoutError("request timed out")
        return Response(url)

    monkeypatch.setattr(nsp_fetcher, "urlopen", fake_urlopen)
    monkeypatch.setattr(nsp_fetcher.time, "sleep", lambda _: None)
    schemes = [
        make_scheme(
            "Missing PDF Award",
            scheme_info_link="https://scholarships.gov.in/404.pdf",
            benefits="Existing benefit",
        ),
        make_scheme(
            "Slow PDF Award",
            scheme_info_link="https://scholarships.gov.in/timeout.pdf",
            eligibility_details="Existing eligibility",
        ),
        make_scheme(
            "Successful PDF Award",
            scheme_info_link="https://scholarships.gov.in/guideline.html",
        ),
    ]

    nsp_fetcher._enrich_guidelines(schemes)

    assert schemes[0]["benefits"] == "Existing benefit"
    assert schemes[1]["eligibility_details"] == "Existing eligibility"
    assert schemes[2]["benefits"] == "New official grant"
    assert attempts["https://scholarships.gov.in/404.pdf"] == 1
    assert attempts["https://scholarships.gov.in/timeout.pdf"] == nsp_fetcher.RETRY_COUNT
    assert attempts["https://scholarships.gov.in/guideline.html"] == 1
    assert "Missing PDF Award" in caplog.text
    assert "Slow PDF Award" in caplog.text


def test_extract_guideline_fields_from_html_sections():
    content = b"""
    <html><body>
      <h2>Benefits:</h2><p>Rs. 20,000 per year</p>
      <p>Student Application Open from: 01-01-2027</p>
      <p>Student Application Open till: 15-03-2027</p>
      <h2>Family Income:</h2><p>Up to Rs. 3 lakh annually</p>
      <h2>Documents Required: Income certificate</h2>
    </body></html>
    """

    fields = nsp_fetcher.extract_guideline_fields(content, "text/html")

    assert fields["benefits"] == "Rs. 20,000 per year"
    assert fields["income_text"] == "Up to Rs. 3 lakh annually"
    assert fields["required_documents"] == "Income certificate"
    assert fields["application_start_date"] == "01-01-2027"
    assert "Benefits:" in fields["eligibility_details"]


def test_guideline_fields_after_12000_characters_are_not_lost():
    content = (
        "<html><body>"
        + ("background details " * 900)
        + "<h2>Benefits:</h2><p>Annual grant</p>"
        + "<h2>Documents Required:</h2><p>Income certificate</p>"
        + "</body></html>"
    ).encode()

    fields, text, was_truncated = nsp_fetcher._extract_guideline_document(
        content,
        "text/html",
    )

    assert not was_truncated
    assert fields["benefits"] == "Annual grant"
    assert fields["required_documents"] == "Income certificate"
    assert len(text) > 12_000


def test_ai_extraction_rejects_values_not_grounded_in_source():
    fields = {column: None for column in nsp_fetcher.DATASET_COLUMNS}
    extracted = dict(fields)
    extracted["benefits_provided"] = "Guaranteed employment"
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(extracted))
            )
        ]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_: response)
        )
    )

    with pytest.raises(ValueError, match="exact source excerpt"):
        nsp_fetcher._extract_missing_fields_with_ai(
            fields,
            "The scholarship benefit is an annual grant.",
            client,
        )


def test_extract_guideline_fields_from_pdf():
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length 49 >>\nstream\n"
        b"BT /F1 12 Tf 72 720 Td (Benefits: Annual grant) Tj ET\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, item in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode() + item + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF".encode()
    )

    fields = nsp_fetcher.extract_guideline_fields(bytes(pdf), "application/pdf")

    assert fields["benefits"] == "Annual grant"


def test_fetch_resource_retries_transient_network_failure(monkeypatch):
    calls = 0

    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b"official page"

        def geturl(self):
            return nsp_fetcher.NSP_URL

    def fake_urlopen(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary network error")
        return Response()

    monkeypatch.setattr(nsp_fetcher, "urlopen", fake_urlopen)
    monkeypatch.setattr(nsp_fetcher.time, "sleep", lambda _: None)
    monkeypatch.setattr(nsp_fetcher, "_assert_robots_allowed", lambda *_: None)

    content, content_type, final_url = nsp_fetcher.fetch_resource(
        nsp_fetcher.NSP_URL,
        retries=2,
    )

    assert calls == 2
    assert content == b"official page"
    assert content_type == "text/html"
    assert final_url == nsp_fetcher.NSP_URL


def test_fetch_resource_honors_retry_after_on_rate_limit(monkeypatch):
    calls = 0
    waits = []

    class Response:
        status = 200
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            return b"official page"

        def geturl(self):
            return nsp_fetcher.NSP_URL

    def fake_urlopen(request, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                {"Retry-After": "7"},
                None,
            )
        return Response()

    monkeypatch.setattr(nsp_fetcher, "urlopen", fake_urlopen)
    monkeypatch.setattr(nsp_fetcher.time, "sleep", waits.append)
    monkeypatch.setattr(nsp_fetcher, "_assert_robots_allowed", lambda *_: None)

    content, _, _ = nsp_fetcher.fetch_resource(
        nsp_fetcher.NSP_URL,
        retries=2,
    )

    assert content == b"official page"
    assert calls == 2
    assert waits == [7.0]


def test_duplicate_detection_updates_only_matching_nsp_source(session_factory):
    scheme = make_scheme("Annual Award")
    record = nsp_fetcher._record_from_scheme(scheme)
    with session_factory() as db:
        db.add(Scholarship(**record))
        db.commit()
        new, review, exact, _ = nsp_fetcher.find_new_schemes([scheme], db)

    assert not new
    assert not review
    assert exact[0]["action"] == "update"


def test_duplicate_detection_skips_exact_cross_source_and_reviews_fuzzy_match(
    session_factory,
):
    with session_factory() as db:
        db.add(
            Scholarship(
                scholarship_name="National Merit Award",
                provider="Ministry One",
                source_filename="legacy.csv",
                source_identifier="legacy:1",
            )
        )
        db.commit()
        new, review, exact, _ = nsp_fetcher.find_new_schemes(
            [
                make_scheme("National Merit Award", "Ministry One"),
                make_scheme("National Merit Awards", "Ministry One"),
                make_scheme("Completely Different Grant", "Ministry Two"),
            ],
            db,
        )

    assert [scheme["scholarship_name"] for scheme in new] == [
        "Completely Different Grant"
    ]
    assert review[0]["scheme"]["scholarship_name"] == "National Merit Awards"
    assert exact[0]["action"] == "exact_existing"


def test_duplicate_detection_uses_official_url_as_review_evidence():
    existing = [
        {
            "id": "legacy-id",
            "name": "Previous Award Name",
            "provider": "NSP Provider",
            "source_filename": "legacy.csv",
            "source_identifier": "legacy:1",
            "official_link": "https://scholarships.gov.in/apply/award-1",
            "normalized": nsp_fetcher.normalize_name("Previous Award Name"),
            "provider_normalized": nsp_fetcher.normalize_name("NSP Provider"),
        }
    ]

    new, review, exact = nsp_fetcher._classify_schemes(
        [
            make_scheme(
                "Updated Award Name",
                official_link="https://scholarships.gov.in/apply/award-1/",
            )
        ],
        existing,
    )

    assert not new
    assert not exact
    assert review[0]["possible_matches"][0]["match_reason"] == "official_url"


def test_ug_pg_and_degree_diploma_variants_are_not_merged():
    existing = [
        {
            "id": "ug-id",
            "name": "ICAR Scholarship Scheme - UG",
            "provider": "ICAR",
            "source_filename": "legacy.csv",
            "source_identifier": "legacy:ug",
            "normalized": nsp_fetcher.normalize_name("ICAR Scholarship Scheme - UG"),
            "provider_normalized": nsp_fetcher.normalize_name("ICAR"),
        },
        {
            "id": "degree-id",
            "name": "Technical Education Degree Scholarship",
            "provider": "State Department",
            "source_filename": "legacy.csv",
            "source_identifier": "legacy:degree",
            "normalized": nsp_fetcher.normalize_name(
                "Technical Education Degree Scholarship"
            ),
            "provider_normalized": nsp_fetcher.normalize_name("State Department"),
        },
    ]

    new, review, exact = nsp_fetcher._classify_schemes(
        [
            make_scheme("ICAR Scholarship Scheme - PG", "ICAR"),
            make_scheme(
                "Technical Education Diploma Scholarship",
                "State Department",
            ),
        ],
        existing,
    )

    assert [scheme["scholarship_name"] for scheme in new] == [
        "ICAR Scholarship Scheme - PG",
        "Technical Education Diploma Scholarship",
    ]
    assert not review
    assert not exact


def test_persist_schemes_inserts_then_updates_without_overwriting_active_flag(session_factory):
    original = make_scheme(
        "Annual Award",
        official_link="https://scholarships.gov.in/specific-apply",
    )
    inserted = nsp_fetcher.persist_schemes(
        [original],
        session_factory=session_factory,
    )
    assert inserted["inserted"] == 1

    updated = make_scheme(
        "Annual Award",
        benefits="Updated annual grant",
        official_link=None,
    )
    with session_factory() as db:
        scholarship = db.query(Scholarship).one()
        scholarship.is_active = True
        db.commit()

    stats = nsp_fetcher.persist_schemes([updated], session_factory=session_factory)

    assert stats["updated"] == 1
    with session_factory() as db:
        scholarship = db.query(Scholarship).one()
        assert scholarship.benefits == "Updated annual grant"
        assert scholarship.official_link == "https://scholarships.gov.in/specific-apply"
        assert scholarship.is_active is True
        assert nsp_fetcher.SOURCE_FILENAME in scholarship.source_filename
        assert db.query(Scholarship).count() == 1


def test_persist_schemes_rolls_back_all_inserts_on_constraint_error(session_factory):
    with session_factory() as db:
        db.execute(
            text(
                "CREATE TRIGGER reject_bad_scheme BEFORE INSERT ON scholarships "
                "WHEN NEW.scholarship_name = 'Bad Award' "
                "BEGIN SELECT RAISE(ABORT, 'rejected'); END"
            )
        )
        db.commit()

    with pytest.raises(IntegrityError):
        nsp_fetcher.persist_schemes(
            [make_scheme("Good Award"), make_scheme("Bad Award")],
            session_factory=session_factory,
        )

    with session_factory() as db:
        assert db.query(Scholarship).count() == 0


def test_discovery_only_pipeline_does_not_persist(monkeypatch, session_factory):
    html = """
    <div class="accordion-item">
      <div class="accordion-header">Ministry One</div>
      <div class="accordion-body"><div class="row mb-4">
        <div>Annual Award (Merit Based Scheme)</div>
        <a href="/guideline.pdf">Specification</a>
      </div></div>
    </div>
    """
    monkeypatch.setattr(nsp_fetcher, "fetch_page", lambda: html)
    monkeypatch.setattr(
        nsp_fetcher,
        "_fetch_resource_details",
        lambda url, validators=None, source_key="nsp": (
            b"<p>Benefits: Annual grant</p>",
            "text/html",
            url,
            None,
            None,
        ),
    )
    monkeypatch.setattr(nsp_fetcher.time, "sleep", lambda _: None)

    report = nsp_fetcher.run_pipeline(
        discovery_only=True,
        session_factory=session_factory,
        ai_client=False,
    )

    assert report["discovery_only"] is True
    assert report["potential_new"] == 1
    assert report["inserted"] == 0
    with session_factory() as db:
        assert db.query(Scholarship).count() == 0
        assert db.query(ScholarshipIngestionRun).count() == 1
        assert db.query(ScholarshipIngestionState).count() == 1
        assert db.query(ScholarshipIngestionEvent).count() == 1
        assert db.query(ScholarshipIngestionSource).one().last_success_at is not None


def test_disabled_source_is_rejected_before_discovery(session_factory, monkeypatch):
    monkeypatch.setattr(
        nsp_fetcher,
        "fetch_page",
        lambda: pytest.fail("disabled sources must not fetch"),
    )

    with pytest.raises(ValueError, match="is not enabled"):
        nsp_fetcher.run_pipeline(
            discovery_only=True,
            session_factory=session_factory,
            source_key="aicte",
            ai_client=False,
        )


def test_listing_fetch_failure_is_recorded_and_propagated(
    monkeypatch,
    session_factory,
):
    def fail_listing():
        raise RuntimeError("listing unavailable")

    monkeypatch.setattr(nsp_fetcher, "fetch_page", fail_listing)

    with pytest.raises(RuntimeError, match="listing unavailable"):
        nsp_fetcher.run_pipeline(
            discovery_only=True,
            session_factory=session_factory,
            ai_client=False,
        )

    with session_factory() as db:
        run = db.query(ScholarshipIngestionRun).one()
        source = db.query(ScholarshipIngestionSource).one()
        assert run.status == "failed"
        assert "listing unavailable" in run.error
        assert "listing unavailable" in source.last_error


def test_incremental_pipeline_reuses_extraction_and_persists_atomically(
    monkeypatch,
    session_factory,
):
    html = """
    <div class="accordion-item">
      <div class="accordion-header">Ministry One</div>
      <div class="accordion-body"><div class="row mb-4">
        <div>Annual Award (Merit Based Scheme)</div>
        <a href="/guideline.html">Guideline</a>
      </div></div>
    </div>
    """
    document = b"""
    <html><body>
      <h2>Eligible Education:</h2><p>Undergraduate</p>
      <h2>Eligible Categories:</h2><p>All categories</p>
      <h2>Minimum Marks:</h2><p>60%</p>
      <h2>Family Income:</h2><p>Up to Rs. 3 lakh annually</p>
      <h2>Benefits:</h2><p>Annual grant</p>
      <h2>Documents Required:</h2><p>Income certificate</p>
    </body></html>
    """
    monkeypatch.setattr(nsp_fetcher, "fetch_page", lambda: html)
    monkeypatch.setattr(nsp_fetcher.time, "sleep", lambda _: None)
    download_calls = []

    def fetch_document(url, validators=None, source_key="nsp"):
        download_calls.append(validators)
        if validators:
            return b"", "", url, "guideline-etag", "yesterday"
        return document, "text/html", url, "guideline-etag", "yesterday"

    monkeypatch.setattr(nsp_fetcher, "_fetch_resource_details", fetch_document)

    class AIClient:
        def __init__(self):
            self.calls = 0
            self.row = {
                column: None for column in nsp_fetcher.DATASET_COLUMNS
            }
            self.row.update(
                {
                    "scholarship_name": "Annual Award",
                    "offered_by": "Ministry One",
                    "current_education": "Undergraduate",
                    "eligible_castes_or_categories": "All categories",
                    "minimum_marks": "60%",
                    "family_income_limit": "Up to Rs. 3 lakh annually",
                    "benefits_provided": "Annual grant",
                    "key_documents_required": "Income certificate",
                    "official_portal_link": nsp_fetcher.NSP_URL,
                    "scheme_info_link": "https://scholarships.gov.in/guideline.html",
                }
            )

            class Completions:
                def __init__(self, owner):
                    self.owner = owner

                def create(self, **kwargs):
                    self.owner.calls += 1
                    return type(
                        "Response",
                        (),
                        {
                            "choices": [
                                type(
                                    "Choice",
                                    (),
                                    {
                                        "message": type(
                                            "Message",
                                            (),
                                            {
                                                "content": json.dumps(
                                                    self.owner.row
                                                )
                                            },
                                        )()
                                    },
                                )()
                            ]
                        },
                    )()

            self.chat = type(
                "Chat",
                (),
                {"completions": Completions(self)},
            )()

    ai_client = AIClient()
    first = nsp_fetcher.run_pipeline(
        discovery_only=True,
        session_factory=session_factory,
        ai_client=ai_client,
    )
    second = nsp_fetcher.run_pipeline(
        discovery_only=True,
        session_factory=session_factory,
        ai_client=ai_client,
    )
    inserted = nsp_fetcher.run_pipeline(
        discovery_only=False,
        session_factory=session_factory,
        ai_client=ai_client,
    )
    unchanged = nsp_fetcher.run_pipeline(
        discovery_only=False,
        session_factory=session_factory,
        ai_client=ai_client,
    )

    assert first["classifications"][0]["classification"] == "NEW"
    assert second["classifications"][0]["classification"] == "NEW"
    assert inserted["inserted"] == 1
    assert inserted["statistics"]["final_record_count"] == 1
    assert inserted["statistics"]["discovered"] == 1
    assert unchanged["classifications"][0]["classification"] == "UNCHANGED"
    assert unchanged["unchanged"] == 1
    assert ai_client.calls == 1
    assert len(download_calls) == 4
    assert download_calls[1] == {
        "etag": "guideline-etag",
        "last_modified": "yesterday",
    }
    with session_factory() as db:
        scholarship = db.query(Scholarship).one()
        assert scholarship.scholarship_name == "Annual Award"
        assert scholarship.active_status == "unknown"
        assert scholarship.is_active is False
        assert db.query(ScholarshipIngestionEvent).count() == 4
        state = db.query(ScholarshipIngestionState).one()
        assert tuple(state.dataset_fields) == nsp_fetcher.DATASET_COLUMNS
        assert state.document_hash == nsp_fetcher.sha256(document).hexdigest()
        persisted_run = (
            db.query(ScholarshipIngestionRun)
            .order_by(ScholarshipIngestionRun.started_at.desc())
            .first()
        )
        hashes = persisted_run.statistics["hashes"][state.source_identifier]
        assert hashes["current"]["document"] == state.document_hash
        assert hashes["previous"]["document"] == state.document_hash
        assert persisted_run.statistics["application_periods"][
            state.source_identifier
        ]["start"] is None


def test_missing_updated_listing_status_preserves_known_application_status(
    monkeypatch,
):
    guideline_url = "https://scholarships.gov.in/guideline.html"
    previous_fields = {
        column: None for column in nsp_fetcher.DATASET_COLUMNS
    }
    previous_fields.update(
        {
            "scholarship_name": "Annual Award",
            "offered_by": "NSP Provider",
            "current_education": "Undergraduate",
            "eligible_castes_or_categories": "All categories",
            "minimum_marks": "60%",
            "family_income_limit": "Up to Rs. 3 lakh annually",
            "benefits_provided": "Old annual grant",
            "key_documents_required": "Income certificate",
            "official_portal_link": nsp_fetcher.NSP_URL,
            "scheme_info_link": guideline_url,
        }
    )
    old_document = b"<h2>Benefits:</h2><p>Old annual grant</p>"
    previous_state = SimpleNamespace(
        guideline_url=guideline_url,
        document_hash=nsp_fetcher.sha256(old_document).hexdigest(),
        content_hash="old-content-hash",
        source_text="Benefits: Old annual grant",
        dataset_fields=previous_fields,
        application_status="open",
        application_deadline="15-03-2027",
        deadline_evidence=(
            "Student Application Open from: 01-01-2027\n"
            "Student Application Open till: 15-03-2027"
        ),
        resolved_guideline_url=guideline_url,
        etag="old-etag",
        last_modified="old-date",
    )
    monkeypatch.setattr(nsp_fetcher.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        nsp_fetcher,
        "_fetch_resource_details",
        lambda url, validators=None, source_key="nsp": (
            b"<h2>Benefits:</h2><p>Updated annual grant</p>",
            "text/html",
            url,
            "new-etag",
            "new-date",
        ),
    )

    result = nsp_fetcher._process_incremental_scheme(
        make_scheme(
            "Annual Award",
            scheme_info_link=guideline_url,
            application_deadline=None,
        ),
        previous_state,
        has_source_record=True,
        base_classification="UPDATED",
        ai_client=False,
    )

    assert result["application_status"] == "open"
    assert result["application_deadline"] == "15-03-2027"
    assert result["deadline_evidence"] == (
        "Student Application Open from: 01-01-2027\n"
        "Student Application Open till: 15-03-2027"
    )
    assert result["application_start_date"] == "01-01-2027"
    assert result["dataset_fields"]["benefits_provided"] == "Updated annual grant"


def test_changed_guideline_updates_existing_scholarship_incrementally(
    monkeypatch,
    session_factory,
):
    html = """
    <div class="accordion-item">
      <div class="accordion-header">Ministry One</div>
      <div class="accordion-body"><div class="row mb-4">
        <div>Annual Award (Merit Based Scheme)</div>
        <a href="/guideline.html">Guideline</a>
      </div></div>
    </div>
    """
    documents = [
        b"<h2>Benefits:</h2><p>Old annual grant</p>",
        b"<h2>Benefits:</h2><p>Updated annual grant</p>",
    ]
    monkeypatch.setattr(nsp_fetcher, "fetch_page", lambda: html)
    monkeypatch.setattr(nsp_fetcher.time, "sleep", lambda _: None)

    def fetch_document(url, validators=None, source_key="nsp"):
        return documents.pop(0), "text/html", url, None, None

    monkeypatch.setattr(nsp_fetcher, "_fetch_resource_details", fetch_document)

    first = nsp_fetcher.run_pipeline(
        discovery_only=False,
        session_factory=session_factory,
        ai_client=False,
    )
    second = nsp_fetcher.run_pipeline(
        discovery_only=False,
        session_factory=session_factory,
        ai_client=False,
    )

    assert first["inserted"] == 1
    assert second["updated"] == 1
    assert second["classifications"][0]["classification"] == "UPDATED"
    with session_factory() as db:
        scholarship = db.query(Scholarship).one()
        assert scholarship.benefits == "Updated annual grant"
    hash_snapshot = next(iter(second["statistics"]["hashes"].values()))
    assert hash_snapshot["previous"]["document"] != hash_snapshot["current"]["document"]


def test_incremental_write_failure_rolls_back_scholarship_and_trace_changes(
    monkeypatch,
    session_factory,
):
    html = """
    <div class="accordion-item">
      <div class="accordion-header">Ministry One</div>
      <div class="accordion-body"><div class="row mb-4">
        <div>Rejected Award (Merit Based Scheme)</div>
        <a href="/guideline.html">Guideline</a>
      </div></div>
    </div>
    """
    monkeypatch.setattr(nsp_fetcher, "fetch_page", lambda: html)
    monkeypatch.setattr(
        nsp_fetcher,
        "_fetch_resource_details",
        lambda url, validators=None, source_key="nsp": (
            b"<p>Benefits: Annual grant</p>",
            "text/html",
            url,
            None,
            None,
        ),
    )
    monkeypatch.setattr(nsp_fetcher.time, "sleep", lambda _: None)
    with session_factory() as db:
        db.execute(
            text(
                "CREATE TRIGGER reject_bad_scheme BEFORE INSERT ON scholarships "
                "WHEN NEW.scholarship_name = 'Rejected Award' "
                "BEGIN SELECT RAISE(ABORT, 'rejected'); END"
            )
        )
        db.commit()
    with pytest.raises(IntegrityError):
        nsp_fetcher.run_pipeline(
            discovery_only=False,
            session_factory=session_factory,
            ai_client=False,
        )
    with session_factory() as db:
        assert db.query(Scholarship).count() == 0
        assert db.query(ScholarshipIngestionState).count() == 0
        assert db.query(ScholarshipIngestionEvent).count() == 0
        assert db.query(ScholarshipIngestionRun).one().status == "failed"


def test_scheduler_runs_again_after_a_failed_cycle(monkeypatch):
    runs = 0

    class StopAfterSecondWait:
        waits = 0

        def is_set(self):
            return False

        def wait(self, seconds):
            self.waits += 1
            assert seconds == nsp_fetcher.SCHEDULE_INTERVAL_SECONDS
            return self.waits == 2

    def fail_once_then_succeed(**kwargs):
        nonlocal runs
        runs += 1
        if runs == 1:
            raise RuntimeError("temporary failure")

    monkeypatch.setattr(nsp_fetcher, "run_pipeline", fail_once_then_succeed)
    nsp_fetcher.run_scheduler(stop_event=StopAfterSecondWait())

    assert runs == 2
