"""Seed small demo data for the Phase 1 database foundation."""

from sqlalchemy import select

from backend.app.database.models.entities import Progress, Roadmap, RoadmapTask, Scheme, User, UserProfile
from backend.app.database.session import SessionLocal


def seed_users() -> list[User]:
    return [
        User(
            email="ananya.demo@example.com",
            hashed_password="demo-hash::ananya123",
            role="USER",
            profile=UserProfile(full_name="Ananya Rao", state="Karnataka", language="Kannada"),
        ),
        User(
            email="meera.demo@example.com",
            hashed_password="demo-hash::meera123",
            role="USER",
            profile=UserProfile(full_name="Meera Sharma", state="Delhi", language="Hindi"),
        ),
        User(
            email="sana.demo@example.com",
            hashed_password="demo-hash::sana123",
            role="ADMIN",
            profile=UserProfile(full_name="Sana Ali", state="Maharashtra", language="English"),
        ),
    ]


def seed_schemes() -> list[Scheme]:
    return [
        Scheme(
            scheme_id="DEMO-SCHEME-001",
            scheme_name="One Stop Centre Scheme",
            description="Integrated support for women affected by violence.",
            category="Women safety",
            state="All States",
            eligibility="Women facing violence or distress.",
            target_group="Women in crisis",
            benefits=["Counselling", "Legal aid", "Temporary shelter"],
            required_documents=["ID proof", "Incident details if available"],
            application_process="Approach the nearest One Stop Centre or district authority.",
            official_url="https://wcd.gov.in/",
            source="Demo seed data based on public policy themes",
            last_verified="2026-08-08",
        ),
        Scheme(
            scheme_id="DEMO-SCHEME-002",
            scheme_name="PM Matru Vandana Yojana",
            description="Maternity benefit support for eligible women.",
            category="Maternity",
            state="All States",
            eligibility="Pregnant and lactating women under applicable criteria.",
            target_group="Pregnant women",
            benefits=["Cash assistance"],
            required_documents=["ID proof", "Pregnancy registration details"],
            application_process="Apply through approved local health channels.",
            official_url="https://wcd.gov.in/",
            source="Demo seed data based on public policy themes",
            last_verified="2026-08-08",
        ),
        Scheme(
            scheme_id="DEMO-SCHEME-003",
            scheme_name="Stand-Up India",
            description="Support for entrepreneurship through bank loans.",
            category="Entrepreneurship",
            state="All States",
            eligibility="Women entrepreneurs meeting lending criteria.",
            target_group="Women entrepreneurs",
            benefits=["Bank loan support", "Business financing pathways"],
            required_documents=["Business plan", "Identity and address proof"],
            application_process="Apply through participating banks or official portal.",
            official_url="https://www.standupmitra.in/",
            source="Demo seed data based on public policy themes",
            last_verified="2026-08-08",
        ),
        Scheme(
            scheme_id="DEMO-SCHEME-004",
            scheme_name="Working Women Hostel",
            description="Accommodation support for working women.",
            category="Housing",
            state="All States",
            eligibility="Working women requiring secure accommodation.",
            target_group="Working women",
            benefits=["Hostel accommodation support"],
            required_documents=["Employment proof", "ID proof"],
            application_process="Contact recognized hostel administrators or local authorities.",
            official_url="https://wcd.gov.in/",
            source="Demo seed data based on public policy themes",
            last_verified="2026-08-08",
        ),
        Scheme(
            scheme_id="DEMO-SCHEME-005",
            scheme_name="National Creche Scheme",
            description="Childcare support for working mothers.",
            category="Social security",
            state="All States",
            eligibility="Working mothers based on local service eligibility.",
            target_group="Working mothers",
            benefits=["Day-care support"],
            required_documents=["Child details", "Employment proof"],
            application_process="Apply through participating centers or district programs.",
            official_url="https://wcd.gov.in/",
            source="Demo seed data based on public policy themes",
            last_verified="2026-08-08",
        ),
    ]


def main() -> None:
    """Seed demo records after migrations have created the tables."""

    with SessionLocal() as session:
        existing_user = session.scalar(select(User.id).limit(1))
        if existing_user is not None:
            print("Demo data already present. Skipping seed.")
            return

        users = seed_users()
        session.add_all(users)
        session.flush()

        roadmap = Roadmap(
            user_id=users[0].id,
            title="Immediate Stabilization Plan",
            summary="Short demo roadmap for legal, documentation, and financial stabilization.",
            status="ACTIVE",
        )
        session.add(roadmap)
        session.flush()

        session.add_all(
            [
                RoadmapTask(
                    roadmap_id=roadmap.id,
                    title="Collect identity documents",
                    description="Gather Aadhaar, bank passbook, and residence proof.",
                    status="IN_PROGRESS",
                    priority="HIGH",
                ),
                RoadmapTask(
                    roadmap_id=roadmap.id,
                    title="Review welfare schemes",
                    description="Check eligibility for immediate support and maternity benefits.",
                    status="PENDING",
                    priority="HIGH",
                ),
                RoadmapTask(
                    roadmap_id=roadmap.id,
                    title="Open independent savings account",
                    description="Create a personal account for direct benefit transfer readiness.",
                    status="PENDING",
                    priority="MEDIUM",
                ),
            ]
        )

        session.add(
            Progress(
                roadmap_id=roadmap.id,
                status="ACTIVE",
                completed_milestones=1,
                missed_milestones=0,
                overdue_tasks=1,
                engagement_history=["intake_complete", "documents_started"],
            )
        )
        session.add_all(seed_schemes())
        session.commit()
        print("Seeded demo users, schemes, roadmap, tasks, and progress.")


if __name__ == "__main__":
    main()
