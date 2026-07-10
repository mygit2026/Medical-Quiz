import os
lines = [
    "from flask import Flask, render_template_string",
    "import pandas as pd",
    "import random, math",
    "app = Flask(__name__)",
    "DF = pd.read_parquet('train-00000-of-00001.parquet')",
    "@app.route('/')",
    "def index():",
    "    pdf = DF.iloc[random.sample(range(len(DF)), 180)]",
    "    qs = []",
    "    for idx, r in pdf.iterrows():",
    "        c = {1:'A',2:'B',3:'C',4:'D'}.get(int(r.get('cop',1)),'A')",
    "        qs.append(f\"<div id='q-{len(qs)+1}' style='background:#fff;padding:20px;margin-bottom:15px;border:1px solid #ccc;border-radius:8px;'><h4>Question {len(qs)+1} of 180</h4><p style='font-weight:bold;margin:10px 0;'>{r.get('question')}</p><label><input type='radio' name='n{idx}' value='A'> A: {r.get('opa')}</label><br><label><input type='radio' name='n{idx}' value='B'> B: {r.get('opb')}</label><br><label><input type='radio' name='n{idx}' value='C'> C: {r.get('opc')}</label><br><label><input type='radio' name='n{idx}' value='D'> D: {r.get('opd')}</label><br><p class='ex' style='display:none;color:green;margin-top:10px;'><b>Correct Option: {c}</b><br><b>Rationale:</b> {r.get('exp')}</p></div>\")",
    "    grid = ''.join([f\"<div onclick='document.getElementById(\\\"q-{i}\\\").scrollIntoView({{behavior:\\\"smooth\\\",block:\\\"center\\\"}})' style='padding:8px;background:#eee;border:1px solid #ccc;text-align:center;cursor:pointer;font-weight:bold;border-radius:4px;'>{i}</div>\" for i in range(1,181)])",
    "    html = f\"\"\"<!DOCTYPE html><html><head><title>NEET PG</title></head><body style='display:flex;font-family:sans-serif;margin:0;height:100vh;overflow:hidden;'><div id='box' style='flex:1;overflow-y:auto;padding:20px;'><h2>PRO NEET PG Elite Simulator</h2><h3 id='t' style='position:fixed;top:10px;right:340px;background:yellow;padding:10px;border-radius:4px;'>03:30:00</h3><form>{''.join(qs)}<button type='button' onclick='sub()' style='width:100%;padding:15px;background:black;color:white;font-size:18px;cursor:pointer;border:none;border-radius:6px;'>Finish Exam</button></form></div><div style='width:300px;border-left:1px solid #ccc;padding:20px;overflow-y:auto;'><h3>PALETTE</h3><div style='display:grid;grid-template-columns:repeat(5,1fr);gap:5px;margin-top:15px;'>{grid}</div></div><script>let s=210*60;setInterval(()=>{{s--;let h=String(Math.floor(s/3600)).padStart(2,\"0\"),m=String(Math.floor((s%3600)/60)).padStart(2,\"0\"),r=String(s%60).padStart(2,\"0\");document.getElementById(\"t\").innerText=h+\":\"+m+\":\"+r;}},1000);function sub(){{document.querySelectorAll(\".ex\").forEach(p=>p.style.display=\"block\");alert(\"Exam Submitted! Scroll through items to view answer keys and explanations.\");document.getElementById('box').scrollTop=0;}}</script></body></html>\"\"\"",
    "    return render_template_string(html)",
    "if __name__ == '__main__':",
    "    app.run(debug=True, port=5000)"
]
with open("app.py", "w", encoding="utf-8") as f: f.write("\n".join(lines))
print("=== COMPLETE REPAIR SUCCESSFUL ===")
