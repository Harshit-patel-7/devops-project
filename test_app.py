import os

# Use a throwaway in-memory database for tests. This must be set BEFORE app is imported.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest

from app import app, db


@pytest.fixture
def client():
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app.test_client()


def add(client, **extra):
    payload = {"title": "Sample task"}
    payload.update(extra)
    return client.post("/api/tasks", json=payload)


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json()["status"] == "healthy"


def test_ready_checks_database(client):
    res = client.get("/ready")
    assert res.status_code == 200
    assert res.get_json()["status"] == "ready"


def test_home_page_loads(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"Task Manager" in res.data
    assert b"Served by" in res.data


def test_create_task_with_details(client):
    res = add(client, title="Finish report", priority="high", category="College", due_date="2030-01-31")
    assert res.status_code == 201
    task = res.get_json()
    assert task["title"] == "Finish report"
    assert task["priority"] == "high"
    assert task["category"] == "College"
    assert task["due_date"] == "2030-01-31"
    assert task["done"] is False


def test_defaults_are_applied(client):
    task = add(client).get_json()
    assert task["priority"] == "medium"
    assert task["category"] == "General"
    assert task["due_date"] is None


def test_empty_title_rejected(client):
    assert add(client, title="   ").status_code == 400


def test_invalid_priority_rejected(client):
    assert add(client, priority="urgent").status_code == 400


def test_invalid_due_date_rejected(client):
    assert add(client, due_date="31-01-2030").status_code == 400


def test_toggle_and_delete(client):
    task_id = add(client).get_json()["id"]
    toggled = client.put(f"/api/tasks/{task_id}/toggle").get_json()
    assert toggled["done"] is True
    client.delete(f"/api/tasks/{task_id}")
    assert client.get("/api/tasks").get_json() == []


def test_toggle_missing_task(client):
    assert client.put("/api/tasks/999/toggle").status_code == 404


def test_edit_task(client):
    task_id = add(client, title="Old title").get_json()["id"]
    res = client.put(f"/api/tasks/{task_id}", json={"title": "New title", "priority": "low", "due_date": None})
    assert res.status_code == 200
    updated = res.get_json()
    assert updated["title"] == "New title"
    assert updated["priority"] == "low"


def test_search_and_filters(client):
    add(client, title="Buy milk", category="Home", priority="low")
    add(client, title="Write essay", category="College", priority="high")
    done_id = add(client, title="Pay rent", category="Home", priority="medium").get_json()["id"]
    client.put(f"/api/tasks/{done_id}/toggle")

    assert len(client.get("/api/tasks?search=essay").get_json()) == 1
    assert len(client.get("/api/tasks?category=Home").get_json()) == 2
    assert len(client.get("/api/tasks?priority=high").get_json()) == 1
    assert len(client.get("/api/tasks?status=done").get_json()) == 1
    assert len(client.get("/api/tasks?status=pending").get_json()) == 2


def test_stats(client):
    add(client, title="Late task", priority="high", due_date="2000-01-01")
    done_id = add(client, title="Finished").get_json()["id"]
    client.put(f"/api/tasks/{done_id}/toggle")

    stats = client.get("/api/stats").get_json()
    assert stats["total"] == 2
    assert stats["completed"] == 1
    assert stats["pending"] == 1
    assert stats["overdue"] == 1
    assert stats["high_pending"] == 1


def test_clear_completed(client):
    done_id = add(client, title="Done one").get_json()["id"]
    add(client, title="Still open")
    client.put(f"/api/tasks/{done_id}/toggle")

    res = client.delete("/api/tasks/completed")
    assert res.get_json()["removed"] == 1
    remaining = client.get("/api/tasks").get_json()
    assert len(remaining) == 1
    assert remaining[0]["title"] == "Still open"