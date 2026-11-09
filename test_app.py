from app import app


def test_health():
    client = app.test_client()
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json()["status"] == "healthy"


def test_home_page_loads():
    client = app.test_client()
    res = client.get("/")
    assert res.status_code == 200
    assert b"Task Manager" in res.data


def test_create_task():
    client = app.test_client()
    res = client.post("/api/tasks", json={"title": "Write tests"})
    assert res.status_code == 201
    task_id = res.get_json()["id"]
    tasks = client.get("/api/tasks").get_json()
    assert any(t["id"] == task_id for t in tasks)


def test_empty_title_rejected():
    client = app.test_client()
    res = client.post("/api/tasks", json={"title": "   "})
    assert res.status_code == 400


def test_toggle_and_delete():
    client = app.test_client()
    task_id = client.post("/api/tasks", json={"title": "Temp"}).get_json()["id"]
    toggled = client.put(f"/api/tasks/{task_id}/toggle").get_json()
    assert toggled["done"] is True
    client.delete(f"/api/tasks/{task_id}")
    tasks = client.get("/api/tasks").get_json()
    assert all(t["id"] != task_id for t in tasks)