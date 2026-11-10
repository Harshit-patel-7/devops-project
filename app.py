import os
import socket
import time
from datetime import date, datetime, timezone

from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

app = Flask(__name__)

# The database address comes from an environment variable, so the SAME code
# runs with SQLite on a laptop and PostgreSQL in Kubernetes.
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///tasks.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

PRIORITIES = ("low", "medium", "high")


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    priority = db.Column(db.String(10), nullable=False, default="medium")
    category = db.Column(db.String(50), nullable=False, default="General")
    due_date = db.Column(db.Date, nullable=True)
    done = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        overdue = bool(self.due_date and not self.done and self.due_date < date.today())
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "category": self.category,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "done": self.done,
            "overdue": overdue,
        }


def parse_due(value):
    """Turn '2026-11-30' into a date. Empty means no due date."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("due_date must be in YYYY-MM-DD format")


def read_fields(data, partial=False):
    """Validate the JSON sent by the browser. Returns (fields, error_message)."""
    fields = {}
    if "title" in data or not partial:
        title = (data.get("title") or "").strip()
        if not title:
            return None, "title is required"
        fields["title"] = title[:200]
    if "priority" in data:
        if data["priority"] not in PRIORITIES:
            return None, "priority must be low, medium or high"
        fields["priority"] = data["priority"]
    if "category" in data:
        fields["category"] = (data["category"] or "").strip()[:50] or "General"
    if "due_date" in data:
        try:
            fields["due_date"] = parse_due(data["due_date"])
        except ValueError as exc:
            return None, str(exc)
    return fields, None


@app.route("/")
def home():
    return render_template(
        "index.html",
        version=os.getenv("APP_VERSION", "1.0.0"),
        host=socket.gethostname(),
    )


@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    query = Task.query

    search = request.args.get("search", "").strip()
    if search:
        query = query.filter(Task.title.ilike(f"%{search}%"))

    category = request.args.get("category", "").strip()
    if category:
        query = query.filter(Task.category == category)

    priority = request.args.get("priority", "").strip()
    if priority in PRIORITIES:
        query = query.filter(Task.priority == priority)

    status = request.args.get("status", "").strip()
    if status == "done":
        query = query.filter(Task.done.is_(True))
    elif status == "pending":
        query = query.filter(Task.done.is_(False))

    tasks = query.order_by(Task.done, Task.id.desc()).all()
    return jsonify([t.to_dict() for t in tasks])


@app.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json(silent=True) or {}
    fields, error = read_fields(data)
    if error:
        return jsonify(error=error), 400
    task = Task(**fields)
    db.session.add(task)
    db.session.commit()
    return jsonify(task.to_dict()), 201


@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
def update_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None:
        return jsonify(error="task not found"), 404
    data = request.get_json(silent=True) or {}
    fields, error = read_fields(data, partial=True)
    if error:
        return jsonify(error=error), 400
    if "done" in data:
        fields["done"] = bool(data["done"])
    for key, value in fields.items():
        setattr(task, key, value)
    db.session.commit()
    return jsonify(task.to_dict())


@app.route("/api/tasks/<int:task_id>/toggle", methods=["PUT"])
def toggle_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None:
        return jsonify(error="task not found"), 404
    task.done = not task.done
    db.session.commit()
    return jsonify(task.to_dict())


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    task = db.session.get(Task, task_id)
    if task is not None:
        db.session.delete(task)
        db.session.commit()
    return jsonify(status="deleted")


@app.route("/api/tasks/completed", methods=["DELETE"])
def clear_completed():
    removed = Task.query.filter(Task.done.is_(True)).delete()
    db.session.commit()
    return jsonify(status="cleared", removed=removed)


@app.route("/api/stats")
def stats():
    tasks = Task.query.all()
    today = date.today()
    pending = [t for t in tasks if not t.done]
    return jsonify(
        total=len(tasks),
        completed=len(tasks) - len(pending),
        pending=len(pending),
        overdue=sum(1 for t in pending if t.due_date and t.due_date < today),
        high_pending=sum(1 for t in pending if t.priority == "high"),
        categories=sorted({t.category for t in tasks}),
    )


@app.route("/health")
def health():
    # Liveness: "is the process itself alive?" Never touches the database.
    return jsonify(status="healthy"), 200


@app.route("/ready")
def ready():
    # Readiness: "can this pod serve users right now?" Needs the database.
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify(status="ready"), 200
    except Exception:
        return jsonify(status="database unavailable"), 503


def init_db(retries=30, delay=2):
    """Create the tables. Retries because the database may start after the app."""
    for attempt in range(1, retries + 1):
        try:
            with app.app_context():
                db.create_all()
            return
        except Exception as exc:
            print(f"Database not ready ({type(exc).__name__}), attempt {attempt}/{retries}", flush=True)
            time.sleep(delay)
    raise RuntimeError("Could not connect to the database")


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)