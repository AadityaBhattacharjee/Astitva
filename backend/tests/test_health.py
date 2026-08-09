def test_health_check(client) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


def test_create_and_list_users(client) -> None:
    create_response = client.post(
        "/api/v1/users/",
        json={
            "email": "phase1.demo@example.com",
            "password": "secret123",
            "role": "USER",
            "full_name": "Phase One User",
            "state": "Karnataka",
            "language": "English",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["email"] == "phase1.demo@example.com"
    assert create_response.json()["profile"]["full_name"] == "Phase One User"

    list_response = client.get("/api/v1/users/")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

