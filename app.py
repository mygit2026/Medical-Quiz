from flask import Flask, render_template_string
import pandas as pd
import random, math, webbrowser, json
from threading import Timer

app = Flask(__name__)
DF = pd.read_parquet("train-00000-of-00001.parquet")

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")

@app.route('/')
def index():
    # Select 180 random questions
    pdf = DF.iloc[random.sample(range(len(DF)), 180)]
    qs = []
    correct_answers = {}

    for idx, r in pdf.iterrows():
        q_num = len(qs) + 1
        
        # Map numerical answer to A, B, C, D
        c = {1:'A', 2:'B', 3:'C', 4:'D'}.get(int(r.get('cop', 1)), 'A')
        correct_answers[f"q{q_num}"] = c
        
        # Safely extract the explanation (handle NaNs and missing data)
        raw_exp = r.get('exp', '')
        if isinstance(raw_exp, float) and math.isnan(raw_exp):
            exp_text = "No explanation provided in the database."
        else:
            exp_text = str(raw_exp).strip()
            if not exp_text or exp_text.lower() == 'nan':
                exp_text = "No explanation provided in the database."
        
        # Escape single quotes for HTML injection
        exp_text = exp_text.replace("'", "&#39;").replace('"', "&quot;")
        
        qs.append(f"""
            <div id='q-{q_num}' class='marrow-target-card' data-cor='{c}'>
                <div class='q-header'>
                    <h4>Question {q_num}</h4>
                </div>
                <p class='q-text'>{r.get('question')}</p>
                <div class='opts-box'>
                    <label id='lbl-{q_num}-A' class='radio-label'><input type='radio' name='n{q_num}' value='A' onchange='mark({q_num})'> <span class='opt-letter'>A</span> {r.get('opa')}</label>
                    <label id='lbl-{q_num}-B' class='radio-label'><input type='radio' name='n{q_num}' value='B' onchange='mark({q_num})'> <span class='opt-letter'>B</span> {r.get('opb')}</label>
                    <label id='lbl-{q_num}-C' class='radio-label'><input type='radio' name='n{q_num}' value='C' onchange='mark({q_num})'> <span class='opt-letter'>C</span> {r.get('opc')}</label>
                    <label id='lbl-{q_num}-D' class='radio-label'><input type='radio' name='n{q_num}' value='D' onchange='mark({q_num})'> <span class='opt-letter'>D</span> {r.get('opd')}</label>
                </div>
                
                <div id='exp-{q_num}' class='explanation-box'>
                    <strong>Explanation:</strong>
                    <p>{exp_text}</p>
                </div>
            </div>
        """)
    
    # Generate compact sidebar buttons
    grid = "".join([f"<div id='btn-{i}' class='nav-btn' onclick='jumpTo({i})'>{i}</div>" for i in range(1, 181)])

    html_template = """
        <html>
            <head>
                <title>Medical Quiz</title>
                <style>
                    /* Reset & Base Typography */
                    body { margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f1f5f9; display: flex; height: 100vh; overflow: hidden; color: #334155; }
                    
                    /* --- LEFT: Main Content Area --- */
                    #main-content { flex-grow: 1; height: 100vh; overflow-y: auto; padding: 40px 20px; display: flex; justify-content: center; box-sizing: border-box; scroll-behavior: smooth; }
                    #container { width: 100%; max-width: 800px; padding-bottom: 60px; }
                    
                    /* Question Cards */
                    .marrow-target-card { background: #ffffff; padding: 32px; margin-bottom: 24px; border: 1px solid #e2e8f0; border-radius: 8px; transition: all 0.2s ease; opacity: 0.6; }
                    .marrow-target-card:hover, .marrow-target-card:focus-within, .marrow-target-card.active { opacity: 1; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05), 0 4px 6px -2px rgba(0,0,0,0.025); border-color: #cbd5e1; transform: translateY(-1px); }
                    
                    .q-header h4 { color: #64748b; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.5px; text-transform: uppercase; margin: 0 0 12px 0; }
                    .q-text { font-weight: 500; font-size: 1.05rem; color: #0f172a; line-height: 1.6; margin-bottom: 24px; }
                    
                    /* Options Styling */
                    .opts-box { display: flex; flex-direction: column; gap: 8px; }
                    .radio-label { display: flex; align-items: center; cursor: pointer; padding: 12px 16px; border-radius: 6px; background: #f8fafc; border: 1px solid transparent; transition: all 0.15s ease; font-size: 0.95rem; }
                    .radio-label:hover { background: #f1f5f9; border-color: #e2e8f0; }
                    input[type="radio"] { margin-right: 12px; width: 16px; height: 16px; accent-color: #2563eb; }
                    .opt-letter { font-weight: 600; color: #475569; margin-right: 8px; font-size: 0.9rem; }
                    
                    /* Post-Submission Styles */
                    .radio-label.correct-ans { background: #dcfce7; border-color: #22c55e; color: #166534; font-weight: 600; }
                    .radio-label.wrong-ans { background: #fee2e2; border-color: #ef4444; color: #991b1b; }
                    
                    .explanation-box { display: none; margin-top: 20px; padding: 16px; background: #eff6ff; border-left: 4px solid #3b82f6; border-radius: 4px; font-size: 0.95rem; color: #1e3a8a; line-height: 1.5; }
                    .explanation-box p { margin: 8px 0 0 0; }
                    
                    /* --- RIGHT: Fixed Sidebar Area --- */
                    #sidebar-wrapper { width: 320px; height: 100vh; background: #ffffff; border-left: 1px solid #e2e8f0; display: flex; flex-direction: column; flex-shrink: 0; box-shadow: -4px 0 15px rgba(0,0,0,0.02); z-index: 10; }
                    .sidebar-header { padding: 20px; border-bottom: 1px solid #e2e8f0; }
                    .sidebar-header h3 { margin: 0; color: #0f172a; font-size: 1rem; text-align: center; font-weight: 600; }
                    
                    #sidebar-scroll-area { flex-grow: 1; overflow-y: auto; padding: 20px; }
                    #sidebar-scroll-area::-webkit-scrollbar { width: 5px; }
                    #sidebar-scroll-area::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
                    #nav-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; }
                    
                    .nav-btn { aspect-ratio: 1; display: flex; align-items: center; justify-content: center; background: #f8fafc; cursor: pointer; border-radius: 4px; font-size: 0.75rem; color: #475569; border: 1px solid #e2e8f0; transition: all 0.15s ease; font-weight: 600; }
                    .nav-btn:hover { background: #e2e8f0; border-color: #cbd5e1; }
                    .nav-btn.completed { background: #10b981; color: white; border-color: #059669; }
                    
                    .sidebar-footer { padding: 20px; border-top: 1px solid #e2e8f0; background: #f8fafc; display: flex; flex-direction: column; gap: 10px; }
                    .btn-grade { padding: 14px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.95rem; transition: background 0.2s; text-align: center; box-shadow: 0 2px 4px rgba(37, 99, 235, 0.2); }
                    .btn-grade:hover { background: #1d4ed8; }
                    .btn-grade:disabled { background: #94a3b8; cursor: not-allowed; box-shadow: none; }
                    .btn-new { padding: 12px; background: transparent; color: #64748b; border: 1px solid #cbd5e1; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.85rem; transition: all 0.2s; text-align: center; }
                    .btn-new:hover { background: #f1f5f9; color: #334155; }

                    /* --- Custom Modal --- */
                    .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(15, 23, 42, 0.6); z-index: 1000; justify-content: center; align-items: center; backdrop-filter: blur(4px); }
                    .modal-content { background: white; padding: 32px; border-radius: 12px; width: 100%; max-width: 400px; box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1); }
                    .modal-content h2 { margin: 0 0 24px 0; color: #0f172a; text-align: center; font-size: 1.5rem; }
                    .stat-row { display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #e2e8f0; font-size: 1rem; color: #334155; }
                    .stat-row:last-of-type { border-bottom: none; margin-bottom: 24px; }
                    .stat-row strong { color: #0f172a; }
                    .stat-score { font-size: 1.25rem; color: #2563eb; font-weight: 700; }
                    .btn-review { width: 100%; padding: 14px; background: #10b981; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 1rem; transition: background 0.2s; }
                    .btn-review:hover { background: #059669; }
                </style>
            </head>
            <body>
                <div id='main-content'>
                    <div id='container'>{{ qs | safe }}</div>
                </div>

                <div id='sidebar-wrapper'>
                    <div class='sidebar-header'>
                        <h3>Question Navigator</h3>
                    </div>
                    <div id='sidebar-scroll-area'>
                        <div id='nav-grid'>{{ grid | safe }}</div>
                    </div>
                    <div class='sidebar-footer'>
                        <button id='submit-btn' class='btn-grade' onclick='finishAndGrade()'>Submit & Grade Exam</button>
                        <button class='btn-new' onclick='window.location.reload()'>Generate New Set</button>
                    </div>
                </div>

                <div id="result-modal" class="modal-overlay">
                    <div class="modal-content">
                        <h2>Exam Summary</h2>
                        <div class="stat-row"><span>Total Questions:</span> <strong id="m-total">180</strong></div>
                        <div class="stat-row"><span>Attempted:</span> <strong id="m-attempted">0</strong></div>
                        <div class="stat-row"><span>Not Attempted:</span> <strong id="m-unattempted">0</strong></div>
                        <div class="stat-row"><span>Incorrect:</span> <strong id="m-incorrect" style="color:#ef4444;">0</strong></div>
                        <div class="stat-row"><span>Correct:</span> <strong id="m-correct" class="stat-score">0</strong></div>
                        <button class="btn-review" onclick="closeModal()">Review Explanations</button>
                    </div>
                </div>

                <script>
                    const answers = {{ answers | safe }};
                    let isSubmitted = false;
                    
                    function mark(qNum) {
                        if(isSubmitted) return; // Prevent clicking if exam is done

                        const navBtn = document.getElementById('btn-' + qNum);
                        if (navBtn) navBtn.classList.add('completed');

                        document.querySelectorAll('.marrow-target-card').forEach(c => c.classList.remove('active'));
                        const card = document.getElementById('q-' + qNum);
                        if (card) card.classList.add('active');
                        
                        const nextNum = qNum + 1;
                        if(nextNum <= 180) {
                            setTimeout(() => { 
                                const nextCard = document.getElementById('q-' + nextNum);
                                if(nextCard) {
                                    const mainContent = document.getElementById('main-content');
                                    const cardTop = nextCard.offsetTop;
                                    const offset = (mainContent.clientHeight - nextCard.clientHeight) / 2;
                                    mainContent.scrollTo({ top: cardTop - offset, behavior: 'smooth' });
                                }
                            }, 350);
                        }
                    }

                    function jumpTo(i) { 
                        const card = document.getElementById('q-'+i);
                        if(card) {
                            const mainContent = document.getElementById('main-content');
                            const cardTop = card.offsetTop;
                            const offset = (mainContent.clientHeight - card.clientHeight) / 2;
                            mainContent.scrollTo({ top: cardTop - offset, behavior: 'smooth' });
                            
                            document.querySelectorAll('.marrow-target-card').forEach(c => c.classList.remove('active'));
                            card.classList.add('active');
                        }
                    }

                    function finishAndGrade() {
                        if(isSubmitted) return;
                        isSubmitted = true;
                        
                        // Disable the submit button
                        const submitBtn = document.getElementById('submit-btn');
                        submitBtn.innerText = 'Exam Submitted';
                        submitBtn.disabled = true;

                        let total = 180;
                        let attempted = 0;
                        let correct = 0;

                        // Grade all questions
                        for (let i = 1; i <= total; i++) {
                            const radios = document.querySelectorAll('input[name="n'+i+'"]');
                            let answered = false;
                            let userChoice = null;

                            // Lock inputs and check if answered
                            radios.forEach(r => {
                                r.disabled = true; 
                                if (r.checked) {
                                    answered = true;
                                    userChoice = r.value;
                                }
                            });

                            if (answered) attempted++;

                            const correctChoice = answers['q'+i];
                            const expBox = document.getElementById('exp-'+i);

                            if (userChoice === correctChoice) {
                                correct++;
                                // Highlight user's correct choice green
                                document.getElementById('lbl-'+i+'-'+userChoice).classList.add('correct-ans');
                            } else {
                                // Highlight the correct choice green so they know what it was
                                document.getElementById('lbl-'+i+'-'+correctChoice).classList.add('correct-ans');
                                
                                // Highlight user's wrong choice red (if they made one)
                                if(userChoice) {
                                    document.getElementById('lbl-'+i+'-'+userChoice).classList.add('wrong-ans');
                                }
                                
                                // Reveal explanation for wrong or unattempted questions
                                if(expBox) expBox.style.display = 'block';
                            }
                        }

                        let incorrect = attempted - correct;
                        let unattempted = total - attempted;

                        // Populate the modal with data
                        document.getElementById('m-attempted').innerText = attempted;
                        document.getElementById('m-unattempted').innerText = unattempted;
                        document.getElementById('m-incorrect').innerText = incorrect;
                        document.getElementById('m-correct').innerText = correct;

                        // Display the Modal
                        document.getElementById('result-modal').style.display = 'flex';
                    }

                    function closeModal() {
                        // Hide modal and scroll back to question 1 for review
                        document.getElementById('result-modal').style.display = 'none';
                        document.getElementById('main-content').scrollTo({ top: 0, behavior: 'smooth' });
                    }

                    // On load, set first card active
                    document.addEventListener('DOMContentLoaded', () => {
                        const firstCard = document.getElementById('q-1');
                        if(firstCard) firstCard.classList.add('active');
                    });
                </script>
            </body>
        </html>
    """

    return render_template_string(html_template, qs="".join(qs), grid=grid, answers=json.dumps(correct_answers))

if __name__ == '__main__':
    Timer(1, open_browser).start()
    app.run(debug=True)