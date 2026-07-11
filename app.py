from flask import Flask, render_template_string
import pandas as pd
import random, math

app = Flask(__name__)
DF = pd.read_parquet("train-00000-of-00001.parquet")

@app.route('/')
def index():
    pdf = DF.iloc[random.sample(range(len(DF)), 180)]
    qs = []
    for idx, r in pdf.iterrows():
        c = {1:'A', 2:'B', 3:'C', 4:'D'}.get(int(r.get('cop', 1)), 'A')
        ex = "" if isinstance(r.get("exp"), float) and math.isnan(r.get("exp")) else str(r.get("exp")).strip()
        qs.append(f"<div id='q-{len(qs)+1}' style='background:#fff;padding:20px;margin-bottom:15px;border:1px solid #cbd5e1;border-radius:12px;'><h4 style='color:#4c1d95;'>Question {len(qs)+1} of 180</h4><p style='font-weight:600;margin:10px 0;'>{r.get('question')}</p><label><input type='radio' name='q{idx}' value='A' onchange='mark({len(qs)+1})'> <b>A:</b> {r.get('opa')}</label><br><label><input type='radio' name='q{idx}' value='B' onchange='mark({len(qs)+1})'> <b>B:</b> {r.get('opb')}</label><br><label><input type='radio' name='q{idx}' value='C' onchange='mark({len(qs)+1})'> <b>C:</b> {r.get('opc')}</label><br><label><input type='radio' name='q{idx}' value='D' onchange='mark({len(qs)+1})'> <b>D:</b> {r.get('opd')}</label><br><p class='ex' style='display:none;color:#16a34a;background:#f0fdf4;padding:10px;margin-top:10px;border-left:4px solid #16a34a;'><b>Correct Option: {c}</b><br><b>Rationale:</b> {ex}</p></div>")
    
    grid = "".join([f"<div id='btn-{i}' onclick='document.getElementById(\"q-{i}\").scrollIntoView({{behavior:\"smooth\",block:\"center\"}})' style='padding:10px;background:#f1f5f9;border:1px solid #cbd5e1;text-align:center;cursor:pointer;font-weight:700;border-radius:6px;'>{i}</div>" for i in range(1, 181)])
    
    html = f"""<!DOCTYPE html><html><head><title>Marrow Simulator</title></head><body style='display:flex;font-family:sans-serif;margin:0;background:#f8fafc;height:100vh;overflow:hidden;'><div id='box' style='flex:1;overflow-y:auto;padding:30px;max-width:800px;margin:0 auto;'><div style='display:flex;justify-content:space-between;border-bottom:2px solid #e2e8f0;padding-bottom:10px;margin-bottom:20px;'><h2 style='color:#4c1d95;'>mMARROW Elite Engine</h2><h3 id='t' style='background:#4c1d95;color:white;padding:5px 10px;border-radius:4px;'>03:30:00</h3></div><form>{''.join(qs)}<button type='button' onclick='sub()' style='width:100%;padding:15px;background:#1e1b4b;color:white;font-size:16px;font-weight:700;cursor:pointer;border:none;border-radius:8px;'>Finish & Grade Exam</button></form></div><div style='width:300px;border-left:1px solid #cbd5e1;padding:20px;overflow-y:auto;background:#fff;'><h3>PALETTE PROGRESS</h3><div style='display:grid;grid-template-columns:repeat(5,1fr);gap:5px;margin-top:15px;'>{grid}</div></div><script>let s=210*60;setInterval(()=>{{s--;let h=String(Math.floor(s/3600)).padStart(2,"0"),m=String(Math.floor((s%3600)/60)).padStart(2,"0"),r=String(s%60).padStart(2,"0");document.getElementById(\"t\").innerText=h+":"+m+":"+r;}},1000);function mark(i){{let b=document.getElementById(\"btn-\"+i);b.style.background=\"#f3e8ff\";b.style.color=\"#4c1d95\";b.style.borderColor=\"#c084fc\";}}function sub(){{document.querySelectorAll(\".ex\").forEach(p=>p.style.display=\"block\");alert(\"Marrow Sheet Submitted! Scroll down to review rationales.\");document.getElementById('box').scrollTop=0;}}</script></body></html>"""
    return render_template_string(html)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
