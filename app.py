import os
import socket
from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

tasks = []
next_id = 1

PAGE = """
<!DOCTYPE html>
<html>
<head>
  <title>Task Manager</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 520px; margin: 40px auto; padding: 0 16px; }
    .add { display: flex; gap: 8px; margin: 16px 0; }
    .add input { flex: 1; padding: 8px; }
    .add button { padding: 8px 14px; cursor: pointer; }
    ul { list-style: none; padding: 0; }
    li { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid #ddd; }
    li.done span { text-decoration: line-through; color: #888; }
    li span { flex: 1; }
    footer { margin-top: 30px; font-size: 12px; color: #666; }
  </style>
</head>
<body>
  <h1>Task Manager</h1>
  <div id="stats">Loading...</div>
  <div class="add">
    <input id="title" placeholder="What needs doing?">
    <button onclick="addTask()">Add</button>
  </div>
  <ul id="list"></ul>
  <footer>Version {{ version }} | Served by: {{ host }}</footer>

  <script>
    async function load() {
      const res = await fetch('/api/tasks');
      const tasks = await res.json();
      const done = tasks.filter(t => t.done).length;
      document.getElementById('stats').textContent = done + ' of ' + tasks.length + ' completed';
      document.getElementById('list').innerHTML = tasks.map(t =>
        '<li class="' + (t.done ? 'done' : '') + '">' +
        '<input type="checkbox" ' + (t.done ? 'checked' : '') + ' onchange="toggle(' + t.id + ')">' +
        '<span>' + t.title.replace(/</g, '&lt;') + '</span>' +
        '<button onclick="removeTask(' + t.id + ')">Delete</button></li>'
      ).join('');
    }
    async function addTask() {
      const input = document.getElementById('title');
      if (!input.value.trim()) return;
      await fetch('/api/tasks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({title: input.value})
      });
      input.value = '';
      load();
    }
    async function toggle(id) { await fetch('/api/tasks/' + id + '/toggle', {method: 'PUT'}); load(); }
    async function removeTask(id) { await fetch('/api/tasks/' + id, {method: 'DELETE'}); load(); }
    load();
  </script>
</body>
</html>
"""


@app.route("/")
def home():
    return render_template_string(
        PAGE,
        version=os.getenv("APP_VERSION", "1.0.0"),
        host=socket.gethostname(),
    )


@app.route("/api/tasks", methods=["GET"])
def list_tasks():
    return jsonify(tasks)


@app.route("/api/tasks", methods=["POST"])
def create_task():
    global next_id
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify(error="title is required"), 400
    task = {"id": next_id, "title": title, "done": False}
    next_id += 1
    tasks.append(task)
    return jsonify(task), 201


@app.route("/api/tasks/<int:task_id>/toggle", methods=["PUT"])
def toggle_task(task_id):
    for task in tasks:
        if task["id"] == task_id:
            task["done"] = not task["done"]
            return jsonify(task)
    return jsonify(error="task not found"), 404


@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id):
    global tasks
    tasks = [t for t in tasks if t["id"] != task_id]
    return jsonify(status="deleted")


@app.route("/health")
def health():
    return jsonify(status="healthy"), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)