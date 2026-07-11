from flask import Flask, render_template_string, jsonify, request
import pandas as pd
import random, json, os, datetime
from threading import Timer
import webbrowser, html

app = Flask(__name__)
# This finds the file in the same folder no matter what
base_path = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(base_path, "train-00000-of-00001.parquet")
DF = pd.read_parquet(file_path)
HISTORY_FILE = "exam_history.json"

def open_browser(): webbrowser.open_new("http://127.0.0.1:5000")

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
    pdf = DF.iloc[random.sample(range(len(DF)), min(180, len(DF)))]
    qs, correct_answers = [], {}
    
    for idx, r in pdf.iterrows():
        q_num = len(qs) + 1
        c = {1:'A', 2:'B', 3:'C', 4:'D'}.get(int(r.get('cop', 1)), 'A')
        correct_answers[f"q{q_num}"] = c
        topic = r.get('topic', 'General')
        exp_text = str(r.get('exp', 'No explanation provided.'))
        
        qs.append(f"""
            <div id='card-{q_num}' class='marrow-target-card'>
                <div class='q-header'>
                    <span>Question {q_num} | Topic: {topic}</span>
                    <button class='flag-btn' onclick='toggleFlag({q_num})' id='f-{q_num}'>⚑ Flag</button>
                </div>
                <p class='q-text'>{r.get('question')}</p>
                <div class='opts-box'>
                    <label id='l-{q_num}-A' class='radio-label'><input type='radio' name='n{q_num}' value='A' onchange='mark({q_num})'> A: {r.get('opa')}</label>
                    <label id='l-{q_num}-B' class='radio-label'><input type='radio' name='n{q_num}' value='B' onchange='mark({q_num})'> B: {r.get('opb')}</label>
                    <label id='l-{q_num}-C' class='radio-label'><input type='radio' name='n{q_num}' value='C' onchange='mark({q_num})'> C: {r.get('opc')}</label>
                    <label id='l-{q_num}-D' class='radio-label'><input type='radio' name='n{q_num}' value='D' onchange='mark({q_num})'> D: {r.get('opd')}</label>
                </div>
                <div id='exp-{q_num}' class='explanation-box'>
                    <strong>Explanation:</strong> 
                    <button onclick="playTTS('{html.escape(exp_text)}')">🔊 Read Aloud</button>
                    <button onclick='stopTTS()'>⏹ Stop</button>
                    <p>{exp_text}</p>
                </div>
            </div>""")
    
    grid = "".join([f"<button id='btn-{i}' class='nav-btn' onclick='jumpTo({i})'>{i}</button>" for i in range(1, 181)])
    return render_template_string(TEMPLATE, qs="".join(qs), grid=grid, answers=json.dumps(correct_answers))

TEMPLATE = """
<html>
<style>
    body { display: flex; margin: 0; font-family: sans-serif; background: #f1f5f9; height: 100vh; overflow: hidden; }
    #main-zone { flex-grow: 1; height: 100vh; overflow-y: auto; padding: 20px; display: flex; justify-content: center; }
    #container { width: 100%; max-width: 800px; }
    
    /* SIDEBAR LAYOUT FIXED */
    #sidebar-zone { width: 320px; height: 100vh; background: #ffffff; border-left: 1px solid #ccc; display: flex; flex-direction: column; }
    #sidebar-content { padding: 20px; display: flex; flex-direction: column; height: 100%; box-sizing: border-box; }
    .nav-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 5px; flex-grow: 1; overflow-y: auto; margin: 15px 0; }
    
    .marrow-target-card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; border: 2px solid transparent; opacity: 0.6; transition: 0.3s; }
    .marrow-target-card.active { opacity: 1; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-color: #2563eb; }
    .radio-label { padding: 12px; display: block; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; cursor: pointer; margin-bottom: 8px; }
    
    .explanation-box { display: none; margin-top: 15px; padding: 15px; background: #dbeafe; border-left: 4px solid #3b82f6; border-radius: 4px; }
    .nav-btn { height: 40px; cursor: pointer; border: 1px solid #ccc; border-radius: 4px; }
    .nav-btn.completed { background: #22c55e; color: white; border: none; }
    .nav-btn.flagged { border: 2px solid orange; }
    
    .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 2000; justify-content: center; align-items: center; }
    .modal-content { background: white; padding: 30px; border-radius: 12px; width: 400px; text-align: center; }
    
    .calc-trigger { position: fixed; bottom: 20px; left: 20px; padding: 15px; background: #334155; color: white; border-radius: 50px; cursor: pointer; z-index: 1000; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .calc-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 15px; }
    .calc-btn { padding: 15px; cursor: pointer; border: none; background: #e2e8f0; border-radius: 6px; font-weight: bold; }
</style>
<body>
    <div id='main-zone'><div id='container'>{{ qs | safe }}</div></div>
    
    <div id='sidebar-zone'>
        <div id='sidebar-content'>
            <h2>PG-NEET</h2>
            <button onclick='location.reload()'>New Set (Refresh)</button>
            <div class='nav-grid'>{{ grid | safe }}</div>
            <button style='padding:15px; background:#2563eb; color:white; border:none; cursor:pointer; font-weight:bold; width:100%;' onclick='finishAndGrade()'>Submit Exam</button>
        </div>
    </div>

    <div id='results-modal' class='modal'>
        <div class='modal-content'>
            <h2 id='stats-title'>Exam Results</h2>
            <div id='stats-detail' style='text-align:left; margin:20px 0;'></div>
            <button onclick="document.getElementById('results-modal').style.display='none'">Review Explanations</button>
        </div>
    </div>

    <div id='calc-modal' class='modal'>
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
        window.onload = () => { document.getElementById('card-1').classList.add('active'); };

        function calcAdd(v) { document.getElementById('calc-display').value += v; }
        function calcClear() { document.getElementById('calc-display').value = ''; }
        function calcSolve() { try { document.getElementById('calc-display').value = eval(document.getElementById('calc-display').value); } catch { document.getElementById('calc-display').value = 'Error'; } }
        function playTTS(txt) { window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(txt)); }
        function stopTTS() { window.speechSynthesis.cancel(); }
        
        function toggleFlag(i) {
            document.getElementById('f-'+i).style.background = (document.getElementById('f-'+i).style.background == 'orange') ? '' : 'orange';
            document.getElementById('btn-'+i).classList.toggle('flagged');
        }

        function jumpTo(i) {
            document.querySelectorAll('.marrow-target-card').forEach(c => c.classList.remove('active'));
            const target = document.getElementById('card-'+i);
            target.classList.add('active');
            target.scrollIntoView({behavior:'smooth'});
        }

        function mark(i) {
            localStorage.setItem('q'+i, document.querySelector('input[name="n'+i+'"]:checked').value);
            document.getElementById('btn-'+i).classList.add('completed');
            setTimeout(() => { if(i < 180) jumpTo(i + 1); }, 300);
        }

        function finishAndGrade() {
            let corr = 0, att = 0;
            for(let i=1; i<=180; i++) {
                let sel = document.querySelector('input[name="n'+i+'"]:checked');
                let corrVal = answers['q'+i];
                document.querySelectorAll('input[name="n'+i+'"]').forEach(r => r.disabled = true);
                if(sel) {
                    att++;
                    if(sel.value === corrVal) { corr++; document.getElementById('l-'+i+'-'+sel.value).style.background='#dcfce7'; }
                    else { document.getElementById('l-'+i+'-'+sel.value).style.background='#fee2e2'; document.getElementById('l-'+i+'-'+corrVal).style.background='#dcfce7'; }
                } else { document.getElementById('l-'+i+'-'+corrVal).style.background='#dcfce7'; }
                document.getElementById('exp-'+i).style.display = 'block';
            }
            document.getElementById('stats-detail').innerHTML = `
                <p><strong>Correct:</strong> ${corr}</p>
                <p><strong>Wrong:</strong> ${att - corr}</p>
                <p><strong>Skipped:</strong> ${180 - att}</p>
                <p><strong>Total:</strong> 180</p>
            `;
            document.getElementById('results-modal').style.display = 'flex';
            fetch('/save_score', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({correct: corr, total: 180})});
        }
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    Timer(1, open_browser).start()
    app.run()