def _scheme_payload(
    *,
    scheme_id: str,
    name: str,
    category: str,
    state: str,
    target_group: str,
    min_age: int | None = None,
    max_age: int | None = None,
    income_limit: int | None = None,
    active_status: bool = True,
) -> dict[str, object]:
    return {
        "scheme_id": scheme_id,
        "name": name,
        "description": f"Demo data for {name}",
        "category": category,
        "state": state,
        "target_group": target_group,
        "min_age": min_age,
        "max_age": max_age,
        "income_limit": income_limit,
        "eligibility": "Structured demo eligibility",
        "age_criteria": None,
        "income_criteria": None,
        "benefits": ["Cash support"],
        "required_documents": ["Identity proof"],
        "application_process": "Apply through the official process.",
        "official_url": "https://www.india.gov.in/",
        "source": "Test data",
        "last_verified": "2026-08-08",
        "active_status": active_status,
    }


def _create_scheme(client, **kwargs: object) -> None:
    response = client.post("/api/v1/schemes/", json=_scheme_payload(**kwargs))
    assert response.status_code == 201


def test_scheme_creation_and_retrieval(client) -> None:
    _create_scheme(
        client,
        scheme_id="SCHEME-001",
        name="Women Entrepreneurship Credit",
        category="Entrepreneurship",
        state="Karnataka",
        target_group="women",
    )

    response = client.get("/api/v1/schemes/")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "Women Entrepreneurship Credit"


def test_scheme_state_filtering(client) -> None:
    _create_scheme(client, scheme_id="SCHEME-002", name="Karnataka Support", category="Financial assistance", state="Karnataka", target_group="single_parent")
    _create_scheme(client, scheme_id="SCHEME-003", name="Delhi Support", category="Financial assistance", state="Delhi", target_group="single_parent")

    response = client.get("/api/v1/schemes/?state=Karnataka")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Karnataka Support"]


def test_scheme_category_filtering(client) -> None:
    _create_scheme(client, scheme_id="SCHEME-004", name="Skill Track", category="Skill development", state="All States", target_group="women")
    _create_scheme(client, scheme_id="SCHEME-005", name="Maternal Care", category="Healthcare", state="All States", target_group="pregnant_women")

    response = client.get("/api/v1/schemes/?category=Skill development")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Skill Track"]


def test_scheme_income_eligibility_filtering(client) -> None:
    _create_scheme(client, scheme_id="SCHEME-006", name="Income Bound Scheme", category="Social security", state="All States", target_group="widow", income_limit=200000)
    _create_scheme(client, scheme_id="SCHEME-007", name="No Income Cap Scheme", category="Social security", state="All States", target_group="widow")

    response = client.get("/api/v1/schemes/eligible?income=180000&target_group=widow")
    assert response.status_code == 200
    assert {item["name"] for item in response.json()} == {"Income Bound Scheme", "No Income Cap Scheme"}

    response = client.get("/api/v1/schemes/eligible?income=250000&target_group=widow")
    assert response.status_code == 200
    assert {item["name"] for item in response.json()} == {"No Income Cap Scheme"}


def test_scheme_age_eligibility_filtering(client) -> None:
    _create_scheme(client, scheme_id="SCHEME-008", name="Young Mothers Scheme", category="Maternity", state="All States", target_group="pregnant_women", min_age=18, max_age=40)
    _create_scheme(client, scheme_id="SCHEME-009", name="Senior Women Support", category="Social security", state="All States", target_group="women", min_age=45)

    response = client.get("/api/v1/schemes/eligible?age=34&target_group=pregnant_women")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Young Mothers Scheme"]

    response = client.get("/api/v1/schemes/eligible?age=34&target_group=women")
    assert response.status_code == 200
    assert response.json() == []


def test_scheme_combined_eligibility_filtering(client) -> None:
    _create_scheme(
        client,
        scheme_id="SCHEME-010",
        name="Single Parent Support Karnataka",
        category="Financial assistance",
        state="Karnataka",
        target_group="single_parent",
        min_age=21,
        max_age=45,
        income_limit=200000,
    )
    _create_scheme(
        client,
        scheme_id="SCHEME-011",
        name="Income Too Low Match",
        category="Financial assistance",
        state="Karnataka",
        target_group="single_parent",
        min_age=21,
        max_age=45,
        income_limit=150000,
    )

    response = client.get(
        "/api/v1/schemes/eligible?state=Karnataka&income=180000&age=34&target_group=single_parent&category=Financial assistance"
    )
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Single Parent Support Karnataka"]


def test_inactive_scheme_exclusion_from_eligible(client) -> None:
    _create_scheme(client, scheme_id="SCHEME-012", name="Inactive Support", category="Healthcare", state="All States", target_group="women", active_status=False)
    _create_scheme(client, scheme_id="SCHEME-013", name="Active Support", category="Healthcare", state="All States", target_group="women", active_status=True)

    response = client.get("/api/v1/schemes/eligible?target_group=women")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Active Support"]
