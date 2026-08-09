"""Approved external resource registry for task-aware guidance."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovedResource:
    resource_id: str
    name: str
    category: str
    description: str
    official_url: str
    applicable_agent_types: tuple[str, ...]


RESOURCES: dict[str, ApprovedResource] = {
    "myscheme": ApprovedResource(
        resource_id="myscheme",
        name="myScheme",
        category="government_scheme",
        description="Government scheme discovery, eligibility, and application guidance.",
        official_url="https://www.myscheme.gov.in/",
        applicable_agent_types=("government", "finance", "healthcare", "employment"),
    ),
    "india_gov": ApprovedResource(
        resource_id="india_gov",
        name="India.gov.in",
        category="government_service",
        description="Central government services and service discovery.",
        official_url="https://www.india.gov.in/",
        applicable_agent_types=("government", "document", "planning", "case_worker"),
    ),
    "digilocker": ApprovedResource(
        resource_id="digilocker",
        name="DigiLocker",
        category="document_service",
        description="Government-issued digital document retrieval and sharing.",
        official_url="https://www.digilocker.gov.in/",
        applicable_agent_types=("document", "government"),
    ),
    "umang": ApprovedResource(
        resource_id="umang",
        name="UMANG",
        category="government_service",
        description="Unified access point for government applications and service status.",
        official_url="https://web.umang.gov.in/",
        applicable_agent_types=("government", "document", "employment", "planning"),
    ),
    "national_career_service": ApprovedResource(
        resource_id="national_career_service",
        name="National Career Service",
        category="employment_service",
        description="Jobs, counselling, and employment service access.",
        official_url="https://www.ncs.gov.in/",
        applicable_agent_types=("employment",),
    ),
    "eshram": ApprovedResource(
        resource_id="eshram",
        name="e-Shram",
        category="employment_service",
        description="Unorganised worker registration and labour-service access.",
        official_url="https://eshram.gov.in/",
        applicable_agent_types=("employment", "finance"),
    ),
    "nalsa": ApprovedResource(
        resource_id="nalsa",
        name="NALSA",
        category="legal_aid",
        description="National legal aid and legal services support.",
        official_url="https://nalsa.gov.in/",
        applicable_agent_types=("legal", "case_worker"),
    ),
    "karnataka_slsa": ApprovedResource(
        resource_id="karnataka_slsa",
        name="Karnataka State Legal Services Authority",
        category="legal_aid",
        description="Karnataka-specific legal aid and legal services support.",
        official_url="https://karnataka.nalsa.gov.in/",
        applicable_agent_types=("legal", "case_worker"),
    ),
}


RESOURCE_TYPE_MAP: dict[str, tuple[str, ...]] = {
    "government_scheme": ("myscheme", "india_gov"),
    "government_service": ("india_gov", "umang"),
    "document_service": ("digilocker", "umang"),
    "employment_service": ("national_career_service", "eshram"),
    "legal_aid": ("nalsa",),
    "state_legal_aid_karnataka": ("karnataka_slsa",),
}


AGENT_DEFAULT_RESOURCES: dict[str, tuple[str, ...]] = {
    "government": ("myscheme", "india_gov", "umang"),
    "document": ("digilocker", "india_gov", "umang"),
    "employment": ("national_career_service", "eshram", "myscheme"),
    "finance": ("myscheme", "india_gov"),
    "healthcare": ("myscheme", "india_gov", "umang"),
    "legal": ("nalsa",),
    "planning": ("india_gov", "umang"),
    "case_worker": ("india_gov",),
}


def get_resource(resource_id: str) -> ApprovedResource | None:
    return RESOURCES.get(resource_id)


def list_resources(resource_ids: list[str]) -> list[ApprovedResource]:
    seen: set[str] = set()
    resources: list[ApprovedResource] = []
    for resource_id in resource_ids:
        if resource_id in seen:
            continue
        resource = get_resource(resource_id)
        if resource is not None:
            resources.append(resource)
            seen.add(resource_id)
    return resources


def map_resource_types(
    resource_types: list[str],
    agent_type: str,
    state: str | None = None,
) -> list[str]:
    resource_ids: list[str] = []
    seen: set[str] = set()

    for resource_type in resource_types:
        for resource_id in RESOURCE_TYPE_MAP.get(str(resource_type), ()):
            if resource_id not in seen:
                resource_ids.append(resource_id)
                seen.add(resource_id)

    for resource_id in AGENT_DEFAULT_RESOURCES.get(agent_type, ()):
        if resource_id not in seen:
            resource_ids.append(resource_id)
            seen.add(resource_id)

    if agent_type == "legal" and state and "karnataka" in state.lower() and "karnataka_slsa" not in seen:
        resource_ids.append("karnataka_slsa")

    return resource_ids
