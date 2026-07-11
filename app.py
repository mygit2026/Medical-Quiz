from flask import Flask, render_template_string, jsonify, request
import random, json, os, datetime, re
from threading import Timer
import webbrowser, html
try:
    import psycopg2 as _psycopg
    _db_driver = 'psycopg2'
except Exception:
    _psycopg = None
    try:
        import psycopg as _psycopg3
        _psycopg = _psycopg3
        _db_driver = 'psycopg'
    except Exception:
        _psycopg = None
        _db_driver = None
from dotenv import load_dotenv
import requests

# Load environment variables for the database
load_dotenv()

app = Flask(__name__)

# This finds the file in the same folder no matter what
base_path = os.path.dirname(os.path.abspath(__file__))
parquet_path = os.path.join(base_path, "train-00000-of-00001.parquet")
csv_path = os.path.join(base_path, "train.csv")
questions_csv_path = os.path.join(base_path, "questions.csv")

# Load dataframe with fallback: import pandas lazily to avoid import-time DB/extension issues.
DF = None
if os.path.exists(parquet_path):
    try:
        import pandas as pd
        DF = pd.read_parquet(parquet_path)
    except Exception as e:
        print(f"Warning: failed to read parquet ({parquet_path}): {e}")

if DF is None:
    if os.path.exists(csv_path):
        try:
            import pandas as pd
            DF = pd.read_csv(csv_path)
        except Exception as e:
            print(f"Error: failed to read fallback CSV ({csv_path}): {e}")
            DF = pd.DataFrame()
    elif os.path.exists(questions_csv_path):
        try:
            import pandas as pd
            DF = pd.read_csv(questions_csv_path)
        except Exception as e:
            print(f"Error: failed to read fallback questions CSV ({questions_csv_path}): {e}")
            DF = pd.DataFrame()
    else:
        print("Warning: no parquet or CSV dataset found; starting with empty DataFrame.")
        DF = pd.DataFrame()
HISTORY_FILE = "exam_history.json"

# Database Connection Helper
def get_db_connection():
    # Make sure DATABASE_URL is set in your .env file
    if not _psycopg:
        raise RuntimeError("No PostgreSQL driver available (psycopg2 or psycopg). DB features disabled.")
    return _psycopg.connect(os.environ.get("DATABASE_URL"))


def fetch_questions_from_supabase(limit=500):
    """Fetch questions from Supabase REST API. Returns list of dicts."""
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_KEY')
    if not url or not key:
        raise RuntimeError('SUPABASE_URL and SUPABASE_KEY must be set in environment')
    if key.startswith('sb_publishable_'):
        raise RuntimeError('SUPABASE_KEY is a publishable key; use the secret key from Supabase Secrets (sb_secret_...) in Render environment variables to read the questions table.')

    # Ensure URL does not end with a slash
    url = url.rstrip('/')
    endpoint = f"{url}/rest/v1/questions"
    params = {
        'select': '*',
        'choice_type': 'eq.single',
        'limit': limit,
    }
    headers = {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Accept': 'application/json'
    }
    resp = requests.get(endpoint, headers=headers, params=params, timeout=15)
    # Log status and number of items to help diagnose RLS/permission issues in hosted logs
    try:
        data = resp.json()
        print(f"Supabase: status={resp.status_code}, items={len(data)}")
    except Exception:
        print(f"Supabase: status={resp.status_code}, body_len={len(resp.content)}")

    if resp.status_code != 200:
        raise RuntimeError(f"Supabase request failed: {resp.status_code} {resp.text}")
    return data


@app.route('/health')
def health():
    """Simple health check that tests Supabase read access."""
    try:
        questions = fetch_questions_from_supabase(limit=1)
        return jsonify({"status": "ok", "available_questions": len(questions)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/debug-questions')
def debug_questions():
    """Return a small JSON sample of questions for debugging (not paginated)."""
    try:
        qs = fetch_questions_from_supabase(limit=20)
        # Only return select fields to keep payload small
        out = [{
            'id': q.get('id'), 'question': q.get('question'), 'cop': q.get('cop')
        } for q in qs]
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def is_conflicting_explanation(exp_text, cop_value):
    if not exp_text:
        return False
    exp_lower = str(exp_text).strip().lower()
    match = re.search(r"ans(?:wer)?[^a-z0-9]*is[^a-z0-9]*['\"]?([abcd])", exp_lower)
    if not match:
        return False
    chosen = match.group(1).upper()
    expected = {1: "A", 2: "B", 3: "C", 4: "D"}.get(int(cop_value or 1), "A")
    return chosen != expected

def open_browser(): webbrowser.open_new("http://127.0.0.1:5000")

# --- EXISTING FUNCTIONALITY ---

@app.route('/save_score', methods=['POST'])
def save_score():
    data = request.json
    data['date'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            try: history = json.load(f)
            except: history = []
    history.append(data)
    with open(HISTORY_FILE, 'w') as f: json.dump(history, f)
    return jsonify({"status": "success"})

@app.route('/')
def index():
    # Fetch questions from Supabase (raise if missing or failing)
    try:
        questions = fetch_questions_from_supabase(limit=1000)
    except Exception as exc:
        error_message = html.escape(str(exc))
        return render_template_string(
            """
            <html><body style='font-family:system-ui, sans-serif; padding:32px; background:#f8fafc; color:#111827;'>
            <h1 style='color:#b91c1c;'>Supabase load error</h1>
            <p>The app could not load questions from Supabase.</p>
            <pre style='background:#ffffff; border:1px solid #e2e8f0; padding:16px; border-radius:12px; overflow-x:auto;'>{{ msg }}</pre>
            <p>Please set <strong>SUPABASE_KEY</strong> in Render to the Supabase <strong>secret</strong> key (sb_secret_...).</p>
            <p>If you only have a publishable key, create/update the Renderrenvironemnt variable to use the secret key.</p>
            </body></html>
            """,
            msg=error_message
        ), 500

    if not questions:
        return "No questions returned from Supabase. Check SUPABASE_URL/SUPABASE_KEY and that `questions` table has rows.", 500

    # Filter out conflicting explanations similar to previous logic
    filtered = []
    for r in questions:
        try:
            if is_conflicting_explanation(r.get('exp', ''), r.get('cop', 1)):
                continue
        except Exception:
            pass
        filtered.append(r)

    if len(filtered) < 180:
        chosen = filtered
    else:
        chosen = random.sample(filtered, 180)

    qs, correct_answers = [], {}
    for idx, r in enumerate(chosen):
        q_num = len(qs) + 1
        try:
            c = {1:'A', 2:'B', 3:'C', 4:'D'}.get(int(r.get('cop', 1)), 'A')
        except Exception:
            c = 'A'
        correct_answers[f"q{q_num}"] = c
        topic = r.get('topic', 'General')
        exp_text = str(r.get('exp', 'No explanation provided.'))
        safe_question = html.escape(str(r.get('question', '')))
        safe_exp_text = html.escape(exp_text, quote=True)
        safe_opa = html.escape(str(r.get('opa', '')))
        safe_opb = html.escape(str(r.get('opb', '')))
        safe_opc = html.escape(str(r.get('opc', '')))
        safe_opd = html.escape(str(r.get('opd', '')))

        qs.append(f"""
            <div id='card-{q_num}' class='marrow-target-card'>
                <div class='q-header'>
                    <span>Question {q_num} | Topic: {topic}</span>
                    <div style='display:flex; align-items:center; gap:10px;'>
                        <span id='status-{q_num}' class='status-chip status-unanswered'>Unvisited</span>
                        <button class='flag-btn' onclick='toggleFlag({q_num})' id='f-{q_num}'>⚑ Flag</button>
                    </div>
                </div>
                <p class='q-text'>{safe_question}</p>
                <div class='opts-box'>
                    <label id='l-{q_num}-A' class='radio-label'><input type='radio' name='n{q_num}' value='A' onchange='mark({q_num})'> A: {safe_opa}</label>
                    <label id='l-{q_num}-B' class='radio-label'><input type='radio' name='n{q_num}' value='B' onchange='mark({q_num})'> B: {safe_opb}</label>
                    <label id='l-{q_num}-C' class='radio-label'><input type='radio' name='n{q_num}' value='C' onchange='mark({q_num})'> C: {safe_opc}</label>
                    <label id='l-{q_num}-D' class='radio-label'><input type='radio' name='n{q_num}' value='D' onchange='mark({q_num})'> D: {safe_opd}</label>
                </div>
                <div id='exp-{q_num}' class='explanation-box'>
                    <strong>Explanation:</strong> 
                    <button type='button' onclick="playTTS(this.getAttribute('data-text'))" data-text='{safe_exp_text}'>🔊 Read Aloud</button>
                    <button type='button' onclick='stopTTS()'>⏹ Stop</button>
                    <p>{safe_exp_text}</p>
                </div>
            </div>""")
    
    grid = "".join([f"<button id='btn-{i}' class='nav-btn' onclick='jumpTo({i})'>{i}</button>" for i in range(1, 181)])
    return render_template_string(TEMPLATE, qs="".join(qs), grid=grid, answers=json.dumps(correct_answers))

# --- NEW DATABASE-BACKED ENGINE (Added below) ---

@app.route('/get-next-set', methods=['GET'])
def get_next_set():
    user_id = 'test_user' 
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = """
    SELECT q.id, q.question, q.exp, q.cop, q.opa, q.opb, q.opc, q.opd
    FROM questions q
    WHERE NOT EXISTS (
        SELECT 1 FROM user_progress up 
        WHERE up.question_id::text = q.id::text 
        AND up.user_id = %s
    )
    AND NOT (
        (q.cop = 1 AND q.exp ~* 'ans(wer)?[^a-z0-9]*is[^a-z0-9]*[b-d]')
        OR (q.cop = 2 AND q.exp ~* 'ans(wer)?[^a-z0-9]*is[^a-z0-9]*[acd]')
        OR (q.cop = 3 AND q.exp ~* 'ans(wer)?[^a-z0-9]*is[^a-z0-9]*[abd]')
        OR (q.cop = 4 AND q.exp ~* 'ans(wer)?[^a-z0-9]*is[^a-z0-9]*[abc]')
    )
    ORDER BY 
        (CASE 
            WHEN (q.cop = 1 AND q.exp ILIKE '%%' || q.opa || '%%') OR
                 (q.cop = 2 AND q.exp ILIKE '%%' || q.opb || '%%') OR
                 (q.cop = 3 AND q.exp ILIKE '%%' || q.opc || '%%') OR
                 (q.cop = 4 AND q.exp ILIKE '%%' || q.opd || '%%')
            THEN 1 ELSE 0 
        END) DESC, RANDOM()
    LIMIT 10;
    """
    cur.execute(query, (user_id,))
    results = cur.fetchall()
    cur.close()
    conn.close()
    
    questions = [{"id": r[0], "question": r[1], "exp": r[2], "cop": r[3], "opa": r[4], "opb": r[5], "opc": r[6], "opd": r[7]} for r in results]
    return jsonify(questions)

@app.route('/save-progress', methods=['POST'])
def save_progress():
    data = request.json
    question_id = data.get('question_id')
    user_id = 'test_user'
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO user_progress (user_id, question_id) VALUES (%s, %s)", (user_id, question_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success"})

# --- EXISTING TEMPLATE ---

TEMPLATE = """
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body { display: flex; flex-wrap: wrap; margin: 0; padding-bottom: 120px; font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; min-height: 100vh; overflow-x: hidden; color: #0f172a; }
        #main-zone { flex: 1 1 0; min-height: 100vh; overflow-y: auto; padding: 24px; display: flex; justify-content: center; background: linear-gradient(180deg,#f8fafc 0%,#e2e8f0 100%); }
        #container { width: 100%; max-width: 900px; }
        #sidebar-zone { width: 340px; min-width: 280px; height: 100vh; background: #ffffff; border-left: 1px solid #d1d5db; display: flex; flex-direction: column; position: sticky; top: 0; }
        #sidebar-content { padding: 24px; display: flex; flex-direction: column; height: 100%; box-sizing: border-box; gap: 18px; }
        .panel { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 16px; padding: 18px; }
        .question-panel { display: flex; flex-direction: column; gap: 16px; background: white; border: 1px solid #e2e8f0; border-radius: 18px; padding: 18px; box-shadow: 0 16px 40px rgba(15,23,42,0.08); flex: 1; overflow: hidden; }
        .question-panel .nav-grid { flex: 1; min-height: 0; overflow-y: auto; }
        .app-title { font-size: 1.8rem; margin: 0; color: #0f172a; letter-spacing: -0.03em; }
        .app-subtitle { margin: 0; color: #475569; font-size: 0.95rem; line-height: 1.6; }
        .topbar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:16px; flex-wrap:wrap; }
        .header-meta { display:flex; flex-direction:column; gap:6px; }
        .header-meta strong { font-size:1rem; color:#0f172a; }
        .header-meta .hint { color:#64748b; font-size:0.93rem; }
        .theme-toggle { border:none; border-radius:999px; padding:10px 16px; background:#eff6ff; color:#1d4ed8; font-weight:700; cursor:pointer; transition:transform 0.2s ease, background-color 0.2s ease; }
        .theme-toggle:hover { transform:translateY(-1px); background:#dbeafe; }
        .progress-pill { margin-bottom:18px; }
        .progress-label { display:flex; justify-content:space-between; align-items:center; gap:10px; font-size:0.95rem; color:#475569; margin-bottom:8px; }
        .progress-track { background:#e2e8f0; border-radius:999px; height:10px; overflow:hidden; }
        .progress-fill { width:0%; height:100%; border-radius:999px; background:linear-gradient(90deg,#3b82f6,#2563eb); transition:width 0.25s ease; }
        .palette-filters { display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }
        .palette-button { border:1px solid #cbd5e1; border-radius:999px; padding:11px 14px; background:white; color:#334155; cursor:pointer; font-size:0.92rem; transition:all 0.2s ease; }
        .palette-button.active { background:#eff6ff; border-color:#60a5fa; color:#1d4ed8; }
        .status-chip { display:inline-flex; padding:6px 12px; border-radius:999px; background:#f8fafc; color:#334155; font-size:0.8rem; font-weight:700; }
        .status-chip.status-answered { background:#dcfce7; color:#166534; }
        .status-chip.status-flagged { background:#ffedd5; color:#9a3412; }
        .status-chip.status-unanswered { background:#e2e8f0; color:#0f172a; }
        .legend { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; color:#475569; font-size:0.85rem; }
        .legend .badge { display:inline-flex; align-items:center; padding:8px 10px; border-radius:999px; background:#f8fafc; border:1px solid #e2e8f0; }
        .legend .badge.note { background:#eef2ff; color:#1d4ed8; }
        .jump-input { min-width:120px; max-width:140px; padding:10px 12px; border-radius:999px; border:1px solid #cbd5e1; outline:none; }
        .timer-label { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; font-size: 0.95rem; color: #475569; margin-bottom: 0.75rem; }
        .timer-badge { background: #e0f2fe; color: #0369a1; padding: 0.6rem 0.95rem; border-radius: 999px; font-weight: 700; font-size: 0.95rem; letter-spacing: 0.01em; box-shadow: inset 0 0 0 1px rgba(14,165,233,0.12); }
        .stat-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
        body.dark { background:#0f172a; color:#e2e8f0; }
        body.dark #main-zone { background: linear-gradient(180deg,#111827 0%,#0f172a 100%); }
        body.dark #sidebar-zone { background:#111827; border-left-color:#334155; }
        body.dark .panel, body.dark .question-panel, body.dark .submit-panel, body.dark .modal-content { background:#111827; border-color:#334155; color:#e5e7eb; }
        body.dark .app-title, body.dark .header-meta strong { color:#f8fafc; }
        body.dark .app-subtitle, body.dark .timer-label, body.dark .progress-label, body.dark .legend, body.dark .status-chip { color:#cbd5e1; }
        body.dark .radio-label { background:#15202b; border-color:#334155; color:#e5e7eb; }
        body.dark .radio-label:hover { background:#1f2937; }
        body.dark .explanation-box { background:#0f172a; border-left:4px solid #3b82f6; }
        body.dark .theme-toggle { background:#1f2937; color:#bfdbfe; }
        body.dark .progress-track { background:#1f2937; }
        body.dark .progress-fill { background:linear-gradient(90deg,#60a5fa,#2563eb); }
        body.dark .palette-button { background:#15202b; border-color:#334155; color:#cbd5e1; }
        body.dark .palette-button.active { background:#1d4ed8; border-color:#3b82f6; color:#eff6ff; }
        body.dark .status-chip { background:#1f2937; color:#cbd5e1; }
        body.dark .status-chip.status-answered { background:#14532d; color:#bbf7d0; }
        body.dark .status-chip.status-flagged { background:#7c2d12; color:#fee2e2; }
        body.dark .status-chip.status-unanswered { background:#334155; color:#cbd5e1; }
        .stat-card { background: white; border: 1px solid #e2e8f0; border-radius: 14px; padding: 14px 16px; box-shadow: 0 10px 30px rgba(15,23,42,0.08); }
        .stat-card span { display: block; font-size: 1rem; color: #64748b; margin-bottom: 6px; }
        .stat-card strong { display: block; font-size: 1.5rem; color: #0f172a; }
        .nav-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; flex-grow: 1; overflow-y: auto; margin-top: 10px; padding-bottom: 10px; }
        .nav-btn { height: 44px; cursor: pointer; border: 1px solid #cbd5e1; border-radius: 12px; width: 100%; background: white; color: #334155; font-weight: 600; transition: transform 0.2s ease, border-color 0.2s ease, background-color 0.2s ease; }
        .nav-btn:hover { transform: translateY(-1px); border-color: #60a5fa; }
        .nav-btn.current { background: #dbeafe; border-color: #3b82f6; color: #1d4ed8; }
        .nav-btn.attempted { background: #dcfce7; border-color: #22c55e; }
        .nav-btn.flagged { background: #ffedd5; border-color: #fb923c; }
        .nav-btn.unanswered { opacity: 0.75; }
        .marrow-target-card { background: white; padding: 22px; margin-bottom: 22px; border-radius: 18px; border: 1px solid transparent; box-shadow: 0 16px 40px rgba(15,23,42,0.06); transition: border-color 0.25s ease, transform 0.2s ease, background-color 0.2s ease; min-height: 150px; }
        .marrow-target-card.active { border-color: #2563eb; transform: translateY(-1px); }
        .q-header { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 16px; font-size: 0.97rem; color: #475569; }
        .q-text { font-size: 1rem; line-height: 1.75; color: #111827; margin-bottom: 18px; }
        .opts-box { display: grid; gap: 12px; }
        .radio-label { padding: 16px; display: block; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; cursor: pointer; margin-bottom: 8px; transition: border-color 0.2s ease, background-color 0.2s ease; }
        .radio-label input { margin-right: 10px; }
        .radio-label:hover { background: #eff6ff; }
        .radio-label.selected { background: #e0f2fe; border-color: #60a5fa; }
        .explanation-box { display: none; margin-top: 18px; padding: 18px; background: #e0f2fe; border-left: 4px solid #0284c7; border-radius: 12px; }
        .flag-btn { border: none; border-radius: 999px; padding: 10px 14px; background: #eef2ff; color: #1e3a8a; cursor: pointer; transition: background-color 0.2s ease; }
        .flag-btn.flagged { background: #ffedd5; color: #b45309; }
        .submit-panel { position: relative; bottom: auto; right: auto; left: auto; z-index: 1; display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; background: #f8fafc; border-top: 1px solid #e2e8f0; border-radius: 0 0 14px 14px; padding: 14px 16px; box-shadow: inset 0 1px 0 rgba(15,23,42,0.04); }
        .question-panel .submit-panel { background: #ffffff; border-top: 1px solid #e2e8f0; border-radius: 0 0 14px 14px; padding: 14px 16px; }
        .submit-status { background: #eff6ff; color: #1d4ed8; padding: 12px 14px; border-radius: 999px; font-weight: 700; letter-spacing: 0.01em; box-shadow: inset 0 0 0 1px rgba(37,99,235,0.12); min-width: 108px; text-align: center; }
        .submit-fixed { background: #2563eb; color: white; border: none; padding: 15px 24px; border-radius: 999px; cursor: pointer; font-weight: 700; box-shadow: 0 14px 34px rgba(37,99,235,0.25); transition: transform 0.2s ease, opacity 0.2s ease; }
        .submit-fixed:hover { transform: translateY(-2px); }
        .action-bar { display: none; position: fixed; inset: auto 0 0 0; z-index: 1008; padding: 14px 18px; background: rgba(255,255,255,0.98); border-top: 1px solid #d1d5db; box-shadow: 0 -12px 30px rgba(15,23,42,0.1); align-items: center; justify-content: space-between; gap: 10px; }
        .action-bar button { border: none; border-radius: 999px; padding: 12px 14px; background: #f8fafc; color: #0f172a; font-weight: 700; cursor: pointer; box-shadow: inset 0 0 0 1px rgba(148,163,184,0.2); }
        .action-bar button.primary { background: #2563eb; color: white; }
        .action-bar button.flag { background: #ffedd5; color: #b45309; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(15,23,42,0.7); z-index: 2000; justify-content: center; align-items: center; padding: 20px; }
        .modal-content { background: white; padding: 30px; border-radius: 18px; width: min(92vw, 480px); text-align: center; box-shadow: 0 24px 60px rgba(15,23,42,0.18); }
        .modal-content h2 { margin-top: 0; color: #0f172a; }
        .modal-actions { display: flex; justify-content: center; gap: 12px; flex-wrap: wrap; margin-top: 22px; }
        .modal-actions button { min-width: 130px; }
        .calc-trigger { position: fixed; bottom: 24px; left: 24px; padding: 14px 18px; background: #334155; color: white; border-radius: 999px; cursor: pointer; z-index: 1000; box-shadow: 0 10px 26px rgba(0,0,0,0.2); }
        .calc-modal .modal-content { max-width: 420px; }
        button, input, label { font-family: inherit; }
        @media (max-width: 1040px) { body { flex-direction: column; } #main-zone, #sidebar-zone { width: 100%; min-height: auto; height: auto; } #sidebar-zone { position: relative; border-left: none; border-top: 1px solid #d1d5db; } .nav-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); } .calc-trigger { right: 20px; left: auto; } }
        @media (max-width: 820px) { .nav-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; } .submit-panel { right: 16px; left: auto; bottom: 16px; } #main-zone { padding: 16px; } .modal-content { padding: 22px; } }
        @media (max-width: 640px) { #sidebar-zone { position: fixed; bottom: 0; left: 0; right: 0; top: auto; width: 100%; height: auto; border-top: 1px solid #d1d5db; } #sidebar-content { flex-direction: column-reverse; padding: 16px; } #main-zone { padding-bottom: 290px; } .submit-panel { right: 16px; left: 16px; bottom: 92px; width: auto; } .action-bar { display: flex; } .nav-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); } }
        @media (max-width: 520px) { .nav-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } .marrow-target-card { padding: 18px; } .radio-label { padding: 14px; font-size: 0.95rem; } .submit-panel { bottom: 100px; } }
    </style>
</head>
<body>
    <div id='main-zone'><div id='container'>{{ qs | safe }}</div></div>
    
    <div id='sidebar-zone'>
        <div id='sidebar-content'>
            <div class='panel'>
                <h1 class='app-title'>PG-NEET</h1>
                <p class='app-subtitle'>Designed for Dr. Shreya MBBS</p>
                <div class='topbar'>
                    <div class='header-meta'>
                        <strong>Exam simulator</strong>
                        <span class='hint'>Use filters, jump controls and quick status preview</span>
                    </div>
                    <button class='theme-toggle' onclick='toggleTheme()' id='theme-toggle'>Dark mode</button>
                </div>
                <div class='progress-pill'>
                    <div class='progress-label'><span>Question progress</span><strong id='progress-percent'>0%</strong></div>
                    <div class='progress-track'><div id='progress-bar' class='progress-fill'></div></div>
                </div>
                <div class='timer-label'>
                    <span>Exam timer</span>
                    <span id='timer-badge' class='timer-badge'>03:00:00</span>
                </div>
                <div class='stat-grid'>
                    <div class='stat-card'><span>Answered</span><strong id='answered-count'>0</strong></div>
                    <div class='stat-card'><span>Flagged</span><strong id='flagged-count'>0</strong></div>
                    <div class='stat-card'><span>Unanswered</span><strong id='unanswered-count'>180</strong></div>
                    <div class='stat-card'><span>Current</span><strong id='current-count'>1</strong></div>
                </div>
            </div>
            <div class='question-panel'>
                <div style='display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap;'>
                    <strong style='color:#0f172a;'>Question Palette</strong>
                    <div style='display:flex; gap:8px; flex-wrap:wrap;'>
                        <button class='submit-fixed' style='padding:10px 14px; font-size:0.92rem;' onclick='loadNewSet()'>New Set</button>
                        <button class='submit-fixed' style='padding:10px 14px; font-size:0.92rem;' onclick='prepareReviewSummary()'>Review</button>
                    </div>
                </div>
                <div class='nav-grid'>{{ grid | safe }}</div>
                <div class='submit-panel'>
                    <div id='current-question-badge' class='submit-status'>Q 1 of 180</div>
                    <button class='submit-fixed' onclick='prepareReviewSummary()'>Submit Exam</button>
                </div>
            </div>
        </div>
    </div>

    <div id='results-modal' class='modal'>
        <div class='modal-content'>
            <h2 id='stats-title'>Exam Results</h2>
            <div id='stats-detail' style='text-align:left; margin:20px 0;'></div>
            <div class='modal-actions'>
                <button onclick="document.getElementById('results-modal').style.display='none'">Close</button>
            </div>
        </div>
    </div>

    <div id='review-modal' class='modal'>
        <div class='modal-content'>
            <h2>Review Before Submit</h2>
            <div id='review-summary-text' style='text-align:left; margin-top:16px; color:#334155;'></div>
            <div class='modal-actions'>
                <button onclick="document.getElementById('review-modal').style.display='none'">Continue Exam</button>
                <button class='primary' onclick='confirmSubmit()'>Submit Anyway</button>
            </div>
        </div>
    </div>

    <div class='action-bar'>
        <button onclick='navigateQuestion(-1)'>← Prev</button>
        <button class='flag' onclick='toggleFlag(currentQuestion)'>Flag</button>
        <button onclick='navigateQuestion(1)'>Next →</button>
        <button class='primary' onclick='prepareReviewSummary()'>Review</button>
    </div>

    <div id='calc-modal' class='modal calc-modal'>
        <div class='modal-content'>
            <h3>Calculator</h3>
            <input id='calc-display' style='width:100%; padding:10px; font-size:18px;' readonly>
            <div class='calc-grid'>
                <button class='calc-btn' onclick="calcAdd('1')">1</button><button class='calc-btn' onclick="calcAdd('2')">2</button><button class='calc-btn' onclick="calcAdd('3')">3</button><button class='calc-btn' onclick="calcAdd('/')">/</button>
                <button class='calc-btn' onclick="calcAdd('4')">4</button><button class='calc-btn' onclick="calcAdd('5')">5</button><button class='calc-btn' onclick="calcAdd('6')">6</button><button class='calc-btn' onclick="calcAdd('*')">*</button>
                <button class='calc-btn' onclick="calcAdd('7')">7</button><button class='calc-btn' onclick="calcAdd('8')">8</button><button class='calc-btn' onclick="calcAdd('9')">9</button><button class='calc-btn' onclick="calcAdd('-')">-</button>
                <button class='calc-btn' onclick="calcAdd('0')">0</button><button class='calc-btn' onclick="calcClear()">C</button><button class='calc-btn' onclick="calcSolve()">=</button><button class='calc-btn' onclick="calcAdd('+')">+</button>
            </div>
            <br><button onclick="document.getElementById('calc-modal').style.display='none'">Close</button>
        </div>
    </div>

    <div class='calc-trigger' onclick="document.getElementById('calc-modal').style.display='flex'">🧮 Calculator</div>

    <script>
        const answers = {{ answers | safe }};
        let currentQuestion = 1;
        const totalQuestions = 180;
        const examDuration = 180 * 60;
        let timeLeft = examDuration;
        const questionState = Array(totalQuestions).fill('not-visited');
        const flaggedSet = new Set();
        let currentFilter = 'all';

        window.onload = () => {
            restoreState();
            setCurrentQuestion(1);
            setupQuestionObserver();
            startTimer();
            updatePaletteStatus();
            updateSummaryCounts();
            setPaletteFilter(currentFilter);
            updateProgress();
            applyTheme();
        };

        function restoreState() {
            const saved = localStorage.getItem('pgneet_exam_state');
            if (!saved) return;
            try {
                const state = JSON.parse(saved);
                if (state.answers) {
                    Object.entries(state.answers).forEach(([key, value]) => {
                        const idx = Number(key.replace('q', ''));
                        const input = document.querySelector(`input[name="n${idx}"][value="${value}"]`);
                        if (input) {
                            input.checked = true;
                            questionState[idx - 1] = 'attempted';
                        }
                    });
                }
                if (Array.isArray(state.flagged)) {
                    state.flagged.forEach(q => flaggedSet.add(q));
                }
                if (typeof state.timeLeft === 'number') {
                    timeLeft = state.timeLeft;
                }
                if (Array.isArray(state.questionState)) {
                    state.questionState.forEach((status, index) => {
                        if (index < totalQuestions) questionState[index] = status;
                    });
                }
                if (state.theme === 'dark') {
                    document.body.classList.add('dark');
                }
                if (state.filter) {
                    currentFilter = state.filter;
                }
                document.querySelectorAll('.radio-label').forEach(label => {
                    const input = label.querySelector('input[type="radio"]');
                    if (input && input.checked) label.classList.add('selected');
                });
                updatePaletteStatus();
                for (let i = 1; i <= totalQuestions; i++) updateQuestionStatus(i);
            } catch (error) {
                console.warn('Could not restore exam state', error);
            }
        }

        function saveState() {
            const answersState = {};
            for (let i = 1; i <= totalQuestions; i++) {
                const sel = document.querySelector(`input[name="n${i}"]:checked`);
                if (sel) {
                    answersState[`q${i}`] = sel.value;
                }
            }
            const state = {
                answers: answersState,
                flagged: Array.from(flaggedSet),
                questionState,
                timeLeft,
                theme: document.body.classList.contains('dark') ? 'dark' : 'light',
                filter: currentFilter,
            };
            localStorage.setItem('pgneet_exam_state', JSON.stringify(state));
            updateSummaryCounts();
            updateProgress();
        }

        function setCurrentQuestion(i) {
            if (i < 1 || i > totalQuestions) return;
            currentQuestion = i;
            const target = document.getElementById(`card-${i}`);
            if (!target) return;
            document.querySelectorAll('.marrow-target-card').forEach(c => c.classList.remove('active'));
            target.classList.add('active');
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            const badge = document.getElementById('current-question-badge');
            if (badge) badge.textContent = `Q ${i} of ${totalQuestions}`;
            document.getElementById('current-count').textContent = i;
            updateCurrentPalette(i);
        }

        function updateCurrentPalette(i) {
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('current'));
            const currentBtn = document.getElementById(`btn-${i}`);
            if (currentBtn) currentBtn.classList.add('current');
        }

        function navigateQuestion(delta) {
            setCurrentQuestion(Math.min(totalQuestions, Math.max(1, currentQuestion + delta)));
        }

        function jumpTo(i) {
            setCurrentQuestion(i);
        }

        function setupQuestionObserver() {
            const cards = document.querySelectorAll('.marrow-target-card');
            if (!cards.length || !window.IntersectionObserver) return;
            const observer = new IntersectionObserver((entries) => {
                const visible = entries.filter(entry => entry.isIntersecting);
                if (!visible.length) return;
                visible.sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
                const topCard = visible[0].target;
                const match = topCard.id.match(/card-(\\d+)/);
                if (match) setCurrentQuestion(Number(match[1]));
            }, { root: null, rootMargin: '-35% 0px -55% 0px', threshold: 0.35 });
            cards.forEach(card => observer.observe(card));
        }

        function calcAdd(v) { document.getElementById('calc-display').value += v; }
        function calcClear() { document.getElementById('calc-display').value = ''; }
        function calcSolve() { try { document.getElementById('calc-display').value = eval(document.getElementById('calc-display').value); } catch { document.getElementById('calc-display').value = 'Error'; } }
        function playTTS(txt) {
            if (!window.speechSynthesis || !txt) return;
            const utterance = new SpeechSynthesisUtterance(String(txt));
            utterance.lang = 'en-US';
            utterance.rate = 1;
            utterance.pitch = 1;
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(utterance);
        }
        function stopTTS() { if (window.speechSynthesis) window.speechSynthesis.cancel(); }

        function toggleFlag(i) {
            const flagBtn = document.getElementById('f-' + i);
            const paletteBtn = document.getElementById('btn-' + i);
            if (!flagBtn || !paletteBtn) return;
            const isFlagged = flaggedSet.has(i);
            if (isFlagged) {
                flaggedSet.delete(i);
                flagBtn.classList.remove('flagged');
                flagBtn.style.background = '';
                paletteBtn.classList.remove('flagged');
            } else {
                flaggedSet.add(i);
                flagBtn.classList.add('flagged');
                flagBtn.style.background = 'orange';
                paletteBtn.classList.add('flagged');
            }
            updateQuestionStatus(i);
            applyPaletteFilter();
            saveState();
        }

        function mark(i) {
            const sel = document.querySelector(`input[name="n${i}"]:checked`);
            if (!sel) return;
            questionState[i - 1] = 'attempted';
            document.querySelectorAll(`#card-${i} .radio-label`).forEach(l => l.classList.remove('selected'));
            const selectedLabel = document.getElementById(`l-${i}-${sel.value}`);
            if (selectedLabel) selectedLabel.classList.add('selected');
            const paletteBtn = document.getElementById('btn-' + i);
            if (paletteBtn) paletteBtn.classList.add('attempted');
            updateQuestionStatus(i);
            applyPaletteFilter();
            saveState();
            setTimeout(() => { if (i < totalQuestions) jumpTo(i + 1); }, 240);
        }

        function updatePaletteStatus() {
            for (let i = 1; i <= totalQuestions; i++) {
                const btn = document.getElementById('btn-' + i);
                if (!btn) continue;
                btn.classList.remove('attempted', 'flagged', 'unanswered');
                if (flaggedSet.has(i)) btn.classList.add('flagged');
                if (questionState[i - 1] === 'attempted') btn.classList.add('attempted');
                if (questionState[i - 1] === 'not-visited') btn.classList.add('unanswered');
                updateQuestionStatus(i);
            }
            updateSummaryCounts();
            updateProgress();
        }

        function updateSummaryCounts() {
            const answered = document.querySelectorAll('.nav-btn.attempted').length;
            const flagged = flaggedSet.size;
            const unanswered = totalQuestions - answered;
            document.getElementById('answered-count').textContent = answered;
            document.getElementById('flagged-count').textContent = flagged;
            document.getElementById('unanswered-count').textContent = unanswered;
        }

        function updateProgress() {
            const answered = document.querySelectorAll('.nav-btn.attempted').length;
            const progress = Math.round((answered / totalQuestions) * 100);
            document.getElementById('progress-percent').textContent = `${progress}%`;
            const bar = document.getElementById('progress-bar');
            if (bar) bar.style.width = `${progress}%`;
        }

        function applyTheme() {
            const toggleBtn = document.getElementById('theme-toggle');
            if (!toggleBtn) return;
            if (document.body.classList.contains('dark')) {
                toggleBtn.textContent = 'Light mode';
            } else {
                toggleBtn.textContent = 'Dark mode';
            }
        }

        function toggleTheme() {
            document.body.classList.toggle('dark');
            applyTheme();
            saveState();
        }

        function setPaletteFilter(mode) {
            currentFilter = mode;
            document.querySelectorAll('.palette-button').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.filter === mode);
            });
            applyPaletteFilter();
            saveState();
        }

        function applyPaletteFilter() {
            document.querySelectorAll('.marrow-target-card').forEach((card, index) => {
                const i = index + 1;
                let visible = true;
                if (currentFilter === 'flagged') visible = flaggedSet.has(i);
                else if (currentFilter === 'unanswered') visible = questionState[i - 1] !== 'attempted';
                else if (currentFilter === 'answered') visible = questionState[i - 1] === 'attempted';
                card.style.display = visible ? 'block' : 'none';
                const btn = document.getElementById('btn-' + i);
                if (btn) btn.style.display = visible ? 'inline-flex' : 'none';
            });
        }

        function jumpToQuestion() {
            const value = Number(document.getElementById('jump-input').value);
            if (value >= 1 && value <= totalQuestions) setCurrentQuestion(value);
        }

        function updateQuestionStatus(i) {
            const chip = document.getElementById(`status-${i}`);
            if (!chip) return;
            if (flaggedSet.has(i)) {
                chip.textContent = 'Flagged';
                chip.className = 'status-chip status-flagged';
            } else if (questionState[i - 1] === 'attempted') {
                chip.textContent = 'Answered';
                chip.className = 'status-chip status-answered';
            } else {
                chip.textContent = 'Unvisited';
                chip.className = 'status-chip status-unanswered';
            }
        }

        function loadNewSet() {
            localStorage.removeItem('pgneet_exam_state');
            window.location.href = '/?fresh=' + Date.now();
        }

        function prepareReviewSummary() {
            const answered = document.querySelectorAll('.nav-btn.attempted').length;
            const flagged = flaggedSet.size;
            const unanswered = totalQuestions - answered;
            const summary = document.getElementById('review-summary-text');
            summary.innerHTML = `
                <p><strong>Answered:</strong> ${answered}</p>
                <p><strong>Flagged:</strong> ${flagged}</p>
                <p><strong>Unanswered:</strong> ${unanswered}</p>
                <p><strong>Current question:</strong> ${currentQuestion}</p>
                <p style='margin-top:12px;color:#475569;'>You can continue reviewing questions or submit your exam now.</p>
            `;
            document.getElementById('review-modal').style.display = 'flex';
        }

        function confirmSubmit() {
            document.getElementById('review-modal').style.display = 'none';
            gradeExam();
        }

        function gradeExam() {
            stopTimer();
            let corr = 0, att = 0;
            for (let i = 1; i <= totalQuestions; i++) {
                const sel = document.querySelector(`input[name="n${i}"]:checked`);
                const corrVal = answers['q' + i];
                document.querySelectorAll(`input[name="n${i}"]`).forEach(r => r.disabled = true);
                if (sel) {
                    att++;
                    if (sel.value === corrVal) {
                        corr++;
                        const correctLabel = document.getElementById(`l-${i}-${sel.value}`);
                        if (correctLabel) correctLabel.style.background = '#dcfce7';
                    } else {
                        const wrongLabel = document.getElementById(`l-${i}-${sel.value}`);
                        if (wrongLabel) wrongLabel.style.background = '#fee2e2';
                        const correctLabel = document.getElementById(`l-${i}-${corrVal}`);
                        if (correctLabel) correctLabel.style.background = '#dcfce7';
                    }
                } else {
                    const correctLabel = document.getElementById(`l-${i}-${corrVal}`);
                    if (correctLabel) correctLabel.style.background = '#dcfce7';
                }
                const exp = document.getElementById('exp-' + i);
                if (exp) exp.style.display = 'block';
            }
            document.getElementById('stats-detail').innerHTML = `
                <p><strong>Correct:</strong> ${corr}</p>
                <p><strong>Wrong:</strong> ${att - corr}</p>
                <p><strong>Skipped:</strong> ${totalQuestions - att}</p>
                <p><strong>Total:</strong> ${totalQuestions}</p>
            `;
            localStorage.removeItem('pgneet_exam_state');
            document.getElementById('results-modal').style.display = 'flex';
            fetch('/save_score', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ correct: corr, total: totalQuestions }) });
        }

        function startTimer() {
            updateTimerUI();
            window.timerInterval = setInterval(() => {
                timeLeft -= 1;
                if (timeLeft <= 0) {
                    stopTimer();
                    document.getElementById('timer-badge').textContent = '00:00:00';
                    prepareReviewSummary();
                    return;
                }
                updateTimerUI();
                saveState();
            }, 1000);
        }

        function stopTimer() {
            if (window.timerInterval) {
                clearInterval(window.timerInterval);
                window.timerInterval = null;
            }
        }

        function updateTimerUI() {
            const hours = Math.floor(timeLeft / 3600);
            const minutes = Math.floor((timeLeft % 3600) / 60);
            const seconds = timeLeft % 60;
            document.getElementById('timer-badge').textContent = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        }

        window.addEventListener('keydown', (event) => {
            if (event.target.tagName === 'INPUT') return;
            if (event.key === 'ArrowRight') return navigateQuestion(1);
            if (event.key === 'ArrowLeft') return navigateQuestion(-1);
            if (event.key.toLowerCase() === 'f') return toggleFlag(currentQuestion);
            if (event.ctrlKey && event.key === 'Enter') return prepareReviewSummary();
        });
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    Timer(1, open_browser).start()
    app.run()