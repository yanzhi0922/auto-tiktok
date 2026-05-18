# -*- coding: utf-8 -*-
"""标准库实现的本地 Dashboard/API 服务。"""

from __future__ import annotations

import html
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from src.dashboard.security import DashboardSecurity
from src.dashboard.state import get_quota_snapshot, get_run_detail, list_runs
from src.tasks.queue import TaskQueue
from src.utils.redaction import redact_obj


LOGIN_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>登录 Auto TikTok</title>
  <style>
    body { margin:0; min-height:100vh; display:grid; place-items:center; font-family:"Microsoft YaHei", Arial, sans-serif; background:#f6f7f9; color:#20242a; }
    form { width:min(360px, calc(100vw - 32px)); background:#fff; border:1px solid #dde2e8; border-radius:8px; padding:22px; }
    h1 { margin:0 0 16px; font-size:18px; }
    label { display:block; font-size:13px; color:#6b7280; margin-bottom:6px; }
    input { width:100%; height:38px; border:1px solid #cfd6df; border-radius:6px; padding:0 10px; }
    button { width:100%; height:38px; margin-top:14px; border:0; border-radius:6px; background:#0f62fe; color:#fff; font-weight:650; cursor:pointer; }
    .error { color:#b42318; min-height:20px; font-size:13px; margin-top:10px; }
  </style>
</head>
<body>
  <form method="post" action="/login">
    <h1>Auto TikTok Dashboard</h1>
    <label>访问令牌</label>
    <input name="token" type="password" autocomplete="current-password" autofocus>
    <button type="submit">登录</button>
    <div class="error">__ERROR__</div>
  </form>
</body>
</html>"""


DASHBOARD_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Auto TikTok Dashboard</title>
  <style>
    :root { color-scheme: light; --bg:#f6f7f9; --panel:#fff; --line:#dde2e8; --text:#20242a; --muted:#6b7280; --ok:#0f7a4f; --bad:#b42318; --warn:#915c00; --accent:#0f62fe; }
    * { box-sizing: border-box; }
    body { margin:0; font-family:"Microsoft YaHei", Arial, sans-serif; background:var(--bg); color:var(--text); }
    header { height:56px; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 20px; border-bottom:1px solid var(--line); background:#fff; position:sticky; top:0; z-index:1; }
    h1 { font-size:18px; margin:0; font-weight:650; }
    main { display:grid; grid-template-columns: 360px 1fr; min-height:calc(100vh - 56px); }
    aside { border-right:1px solid var(--line); background:#fff; padding:14px; overflow:auto; }
    section { padding:18px; overflow:auto; }
    button { border:1px solid var(--line); background:#fff; color:var(--text); min-height:32px; padding:0 10px; border-radius:6px; cursor:pointer; }
    button.primary { background:var(--accent); color:#fff; border-color:var(--accent); }
    button.danger { border-color:#f3b5ae; color:#b42318; }
    button:disabled { opacity:.55; cursor:not-allowed; }
    input, select { height:32px; border:1px solid var(--line); border-radius:6px; padding:0 9px; background:#fff; }
    label { color:var(--muted); font-size:12px; display:block; margin-bottom:4px; }
    .toolbar { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .run { width:100%; text-align:left; padding:10px; border:1px solid var(--line); border-radius:8px; background:#fff; margin-bottom:8px; cursor:pointer; }
    .run strong { display:block; font-size:13px; }
    .muted { color:var(--muted); font-size:12px; }
    .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap:10px; margin-bottom:14px; }
    .metric, .panel { background:#fff; border:1px solid var(--line); border-radius:8px; padding:12px; }
    .metric .value { font-size:22px; font-weight:700; margin-top:6px; }
    .content { background:#fff; border:1px solid var(--line); border-radius:8px; padding:14px; margin-bottom:12px; }
    .row { display:flex; gap:10px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
    .badge { display:inline-block; padding:2px 8px; border-radius:99px; background:#eef2f7; font-size:12px; margin:2px; }
    .badge.ok { background:#e7f7ef; color:var(--ok); }
    .badge.bad { background:#fdecec; color:var(--bad); }
    .badge.warn { background:#fff4d6; color:var(--warn); }
    .actions { display:flex; gap:6px; flex-wrap:wrap; margin-top:10px; }
    .stack { display:grid; gap:10px; }
    pre { background:#10151f; color:#d7e1f3; padding:12px; border-radius:8px; overflow:auto; max-height:260px; }
    @media (max-width: 920px) { main { grid-template-columns:1fr; } aside { border-right:0; border-bottom:1px solid var(--line); } }
  </style>
</head>
<body>
  <header>
    <h1>Auto TikTok Dashboard</h1>
    <div class="toolbar">
      <button onclick="loadQuota(true)">刷新配额</button>
      <button onclick="loadTasks()">刷新任务</button>
      <button class="primary" onclick="loadRuns()">刷新运行</button>
      __LOGOUT_BUTTON__
    </div>
  </header>
  <main>
    <aside class="stack">
      <div id="quota" class="grid"></div>
      <div class="panel">
        <strong>新建生成任务</strong>
        <div style="height:10px"></div>
        <label>数量</label>
        <input id="dailyCount" type="number" min="1" max="20" value="1" style="width:80px">
        <label style="margin-top:8px">内容类型（逗号分隔，可空）</label>
        <input id="dailyTypes" placeholder="生活技巧,知识科普" style="width:100%">
        <div class="actions">
          <button class="primary" onclick="enqueueDaily()">加入队列</button>
        </div>
      </div>
      <div class="panel">
        <strong>Autopilot 全自动</strong>
        <div style="height:10px"></div>
        <label>目标成片数量</label>
        <input id="autoCount" type="number" min="1" max="20" value="1" style="width:80px">
        <label style="margin-top:8px">最低评分</label>
        <input id="autoMinScore" type="number" min="0" max="100" value="65" style="width:80px">
        <label style="margin-top:8px">内容类型（逗号分隔，可空）</label>
        <input id="autoTypes" placeholder="生活技巧,知识科普" style="width:100%">
        <label style="margin-top:8px">发布方式</label>
        <select id="autoProvider">
          <option value="manual">导出发布包</option>
          <option value="auto">自动选择</option>
          <option value="tiktok">TikTok API</option>
        </select>
        <div class="actions">
          <button class="primary" onclick="enqueueAutopilot()">启动 Autopilot</button>
        </div>
      </div>
      <div>
        <h2 style="font-size:14px">运行历史</h2>
        <div id="runs"></div>
      </div>
    </aside>
    <section class="stack">
      <div id="tasks" class="panel"></div>
      <div id="detail" class="muted">选择左侧运行查看详情。</div>
    </section>
  </main>
  <script>
    const CSRF_TOKEN = "__CSRF_TOKEN__";
    async function api(path, options={}) {
      const opts = {...options};
      opts.headers = {...(opts.headers || {})};
      if ((opts.method || 'GET').toUpperCase() !== 'GET') opts.headers['X-CSRF-Token'] = CSRF_TOKEN;
      const res = await fetch(path, opts);
      let data = {};
      try { data = await res.json(); } catch (_) {}
      if (res.status === 401) { location.href = '/login'; return {}; }
      if (!res.ok) throw new Error(data.error || res.statusText);
      return data;
    }
    function metric(label, value, extra='') {
      return `<div class="metric"><div class="muted">${label}</div><div class="value">${value}</div><div class="muted">${extra}</div></div>`;
    }
    function badge(status) {
      const cls = status === 'succeeded' ? 'ok' : (status === 'failed' ? 'bad' : (status === 'running' ? 'warn' : ''));
      return `<span class="badge ${cls}">${status || 'unknown'}</span>`;
    }
    async function loadQuota(refresh=false) {
      const q = await api('/api/quota' + (refresh ? '?refresh=1' : ''));
      document.getElementById('quota').innerHTML = [
        metric('文本 5h', q.text_5h?.remaining ?? '-', '剩余'),
        metric('TTS', q.tts?.remaining ?? '-', '字符'),
        metric('图片', q.image?.remaining ?? '-', '张'),
        metric('视频', q.video?.remaining ?? '-', '个'),
        metric('音乐', q.music?.remaining ?? '-', '首')
      ].join('');
    }
    async function loadRuns() {
      const runs = await api('/api/runs');
      document.getElementById('runs').innerHTML = runs.map(r => `
        <button class="run" onclick="loadRun(${JSON.stringify(r.date)}, ${JSON.stringify(r.run_id)})">
          <strong>${r.date} / ${r.run_id}</strong>
          <span class="muted">${r.content_count} 条内容 · ${r.modified_at}</span>
        </button>`).join('') || '<div class="muted">暂无运行记录</div>';
    }
    async function loadTasks() {
      const tasks = await api('/api/tasks');
      document.getElementById('tasks').innerHTML = `<div class="row"><strong>任务队列</strong><span class="muted">${tasks.length} 条</span></div>` +
        (tasks.slice(0, 12).map(t => `
          <div style="border-top:1px solid var(--line); padding-top:8px; margin-top:8px">
            <div class="row"><span>${t.task_type}</span>${badge(t.status)}</div>
            <div class="muted">${t.id} · ${t.updated_at}</div>
            ${t.error ? `<pre>${t.error}</pre>` : ''}
            ${t.status === 'queued' || t.status === 'running' ? `<button class="danger" onclick="cancelTask('${t.id}')">取消</button>` : ''}
          </div>`).join('') || '<div class="muted">暂无任务</div>');
    }
    function assetStatus(assets, name) {
      const item = assets?.[name];
      if (!item) return '<span class="badge">未计划</span>';
      const cls = item.status === 'succeeded' ? 'ok' : (item.status === 'failed' ? 'bad' : '');
      return `<span class="badge ${cls}">${name}: ${item.status}</span>`;
    }
    async function loadRun(date, runId) {
      const detail = await api(`/api/runs/${date}/${runId}`);
      document.getElementById('detail').innerHTML = `
        <div class="row"><h2 style="margin:0;font-size:18px">${detail.date} / ${detail.run_id}</h2><span class="muted">${detail.path}</span></div>
        <div style="height:12px"></div>
        ${detail.contents.map(c => `
          <div class="content">
            <div class="row">
              <div>
                <strong>${String(c.index).padStart(3,'0')} · ${c.topic || '未命名'}</strong>
                <div class="muted">${c.content_type || '-'} · score ${c.score ?? '-'}</div>
              </div>
              ${badge(c.status)}
            </div>
            <div style="margin-top:10px">
              ${['audio','video','thumbnail','subtitle','final_video','cover','music'].map(name => assetStatus(c.assets, name)).join(' ')}
            </div>
            ${c.error ? `<pre>${c.error}</pre>` : ''}
            <div class="actions">
              ${['tts','video','thumbnail','subtitle','compose','cover','titles'].map(asset => {
                const planArg = JSON.stringify(c.video_plan_path);
                const assetArg = JSON.stringify(asset);
                return `<button ${c.video_plan_path ? '' : 'disabled'} onclick='regen(${planArg}, ${assetArg})'>重生成 ${asset}</button>`;
              }).join('')}
              <button ${c.video_plan_path ? '' : 'disabled'} onclick='publishManual(${JSON.stringify(c.video_plan_path)})'>导出发布包</button>
              <button ${c.video_plan_path ? '' : 'disabled'} onclick='publishTikTok(${JSON.stringify(c.video_plan_path)})'>发布到 TikTok</button>
            </div>
          </div>`).join('')}
        <details><summary>原始报告</summary><pre>${JSON.stringify(detail.report || detail.manifest || {}, null, 2)}</pre></details>`;
    }
    async function regen(planPath, asset) {
      if (!planPath) return;
      if (!confirm(`确认重生成 ${asset}？这可能消耗 API 额度。`)) return;
      await api('/api/regenerate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({plan_path: planPath, asset})
      });
      await loadTasks();
      alert('已加入任务队列');
    }
    async function publishManual(planPath) {
      await api('/api/publish', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({plan_path: planPath, provider: 'manual'})
      });
      await loadTasks();
      alert('已加入手动发布包导出队列');
    }
    async function publishTikTok(planPath) {
      if (!confirm('确认调用 TikTok 官方发布 API？需要已配置 OAuth access token。')) return;
      await api('/api/publish', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({plan_path: planPath, provider: 'tiktok'})
      });
      await loadTasks();
      alert('已加入 TikTok 发布队列');
    }
    async function enqueueDaily() {
      if (!confirm('确认加入每日生成任务？这会消耗 API 额度。')) return;
      await api('/api/tasks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          task_type: 'generate_daily',
          payload: {count: Number(document.getElementById('dailyCount').value || 1), content_types: document.getElementById('dailyTypes').value}
        })
      });
      await loadTasks();
    }
    async function enqueueAutopilot() {
      if (!confirm('确认启动 Autopilot？它会自动选题、生成、修复并导出发布包。')) return;
      await api('/api/tasks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          task_type: 'autopilot_run',
          payload: {
            count: Number(document.getElementById('autoCount').value || 1),
            min_score: Number(document.getElementById('autoMinScore').value || 65),
            content_types: document.getElementById('autoTypes').value,
            publish_provider: document.getElementById('autoProvider').value
          }
        })
      });
      await loadTasks();
    }
    async function cancelTask(taskId) {
      await api(`/api/tasks/${taskId}/cancel`, {method: 'POST'});
      await loadTasks();
    }
    loadQuota(false).catch(console.error);
    loadRuns().catch(console.error);
    loadTasks().catch(console.error);
    setInterval(loadTasks, 5000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    base_dir = Path("output")
    security = DashboardSecurity()
    task_queue: TaskQueue | None = None

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def _session(self):
        return self.security.get_session(self.headers.get("Cookie"))

    def _queue(self) -> TaskQueue:
        if self.task_queue is None:
            self.task_queue = TaskQueue(base_dir=self.base_dir)
        return self.task_queue

    def _require_auth(self) -> bool:
        if self.security.is_authenticated(self._session()):
            return True
        self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
        return False

    def _require_csrf(self) -> bool:
        session = self._session()
        if self.security.validate_csrf(
            session=session,
            header_value=self.headers.get("X-CSRF-Token"),
            cookie_header=self.headers.get("Cookie"),
        ):
            return True
        self._send_json({"error": "csrf validation failed"}, HTTPStatus.FORBIDDEN)
        return False

    def _send_json(self, payload, status=HTTPStatus.OK, headers=None):
        body = json.dumps(redact_obj(payload), ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, content: str, headers=None):
        body = content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; connect-src 'self'")
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, headers=None):
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _read_form_body(self):
        from urllib.parse import parse_qs

        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        return {key: values[0] if values else "" for key, values in parse_qs(body).items()}

    def do_GET(self):  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/healthz":
                self._send_json({"status": "ok"})
                return
            if parsed.path == "/login":
                self._send_html(LOGIN_HTML.replace("__ERROR__", ""))
                return
            if parsed.path == "/logout":
                self.security.clear_session(self.headers.get("Cookie"))
                self._redirect("/login", headers=self.security.clear_headers())
                return
            session, created = self.security.ensure_session(self.headers.get("Cookie"))
            cookie_headers = self.security.session_headers(session) if created else []
            if parsed.path == "/":
                if not self.security.is_authenticated(session):
                    self._redirect("/login", headers=cookie_headers)
                    return
                logout_button = (
                    "<button onclick=\"location.href='/logout'\">退出</button>"
                    if self.security.auth_required
                    else ""
                )
                body = (
                    DASHBOARD_HTML
                    .replace("__CSRF_TOKEN__", html.escape(session.csrf_token))
                    .replace("__LOGOUT_BUTTON__", logout_button)
                )
                self._send_html(body, headers=cookie_headers)
                return
            if not self._require_auth():
                return
            if parsed.path == "/api/quota":
                query = parse_qs(parsed.query)
                self._send_json(get_quota_snapshot(refresh=query.get("refresh") == ["1"]))
                return
            if parsed.path == "/api/runs":
                self._send_json(list_runs(self.base_dir))
                return
            if parsed.path == "/api/tasks":
                self._send_json(self._queue().list_tasks())
                return
            if parsed.path.startswith("/api/tasks/"):
                parts = parsed.path.split("/")
                if len(parts) == 4:
                    task = self._queue().get_task(parts[3])
                    self._send_json(task or {"error": "not found"}, HTTPStatus.OK if task else HTTPStatus.NOT_FOUND)
                    return
            if parsed.path.startswith("/api/runs/"):
                _, _, _, date, run_id = parsed.path.split("/", 4)
                self._send_json(get_run_detail(base_dir=self.base_dir, date=date, run_id=run_id))
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/login":
                form = self._read_form_body()
                try:
                    session = self.security.authenticate(form.get("token", ""))
                except PermissionError:
                    self._send_html(LOGIN_HTML.replace("__ERROR__", "令牌错误"))
                    return
                self._redirect("/", headers=self.security.session_headers(session))
                return
            if not self._require_auth() or not self._require_csrf():
                return
            if parsed.path == "/api/regenerate":
                body = self._read_json_body()
                task = self._queue().enqueue(
                    "regenerate_asset",
                    {
                        "asset": str(body.get("asset") or ""),
                        "plan_path": body.get("plan_path"),
                        "content_dir": body.get("content_dir"),
                    },
                )
                self._send_json({"task": task.__dict__}, HTTPStatus.ACCEPTED)
                return
            if parsed.path == "/api/publish":
                body = self._read_json_body()
                task = self._queue().enqueue(
                    "publish",
                    {
                        "provider": str(body.get("provider") or "manual"),
                        "plan_path": body.get("plan_path"),
                    },
                )
                self._send_json({"task": task.__dict__}, HTTPStatus.ACCEPTED)
                return
            if parsed.path == "/api/tasks":
                body = self._read_json_body()
                task = self._queue().enqueue(
                    str(body.get("task_type") or ""),
                    dict(body.get("payload") or {}),
                )
                self._send_json({"task": task.__dict__}, HTTPStatus.ACCEPTED)
                return
            if parsed.path.startswith("/api/tasks/") and parsed.path.endswith("/cancel"):
                task_id = parsed.path.split("/")[-2]
                self._send_json(self._queue().cancel(task_id))
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def _coerce_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def run_dashboard(
    *,
    host: str = "127.0.0.1",
    port: int = 7860,
    base_dir: str | Path = "output",
) -> ThreadingHTTPServer:
    security = DashboardSecurity.from_env()
    local_only = _coerce_bool(os.getenv("AUTO_TIKTOK_DASHBOARD_LOCAL_ONLY"), False)
    if (
        not security.auth_required
        and host not in {"127.0.0.1", "localhost", "::1"}
        and not local_only
        and not _coerce_bool(os.getenv("AUTO_TIKTOK_ALLOW_UNAUTHENTICATED_DASHBOARD"), False)
    ):
        raise RuntimeError(
            "Dashboard 绑定非本地地址时必须设置 AUTO_TIKTOK_DASHBOARD_TOKEN，"
            "或显式设置 AUTO_TIKTOK_DASHBOARD_LOCAL_ONLY=true 并确保端口只映射到本机。"
        )

    task_queue = TaskQueue(
        base_dir=base_dir,
        max_workers=int(os.getenv("AUTO_TIKTOK_TASK_WORKERS", "1")),
    )
    task_queue.start()
    handler = type(
        "ConfiguredDashboardHandler",
        (DashboardHandler,),
        {
            "base_dir": Path(base_dir),
            "security": security,
            "task_queue": task_queue,
        },
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Dashboard running at http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        task_queue.stop()
    return server
