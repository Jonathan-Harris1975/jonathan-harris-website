#!/usr/bin/env python3
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "downloads" / "ai-glossary-cheat-sheet" / "ai-glossary-cheat-sheet.pdf"
TERMS = [
    ("Artificial intelligence (AI)", "Software designed to perform tasks that normally require human judgement, pattern recognition or decision-making."),
    ("Machine learning (ML)", "AI systems that learn patterns from data rather than relying only on hand-written rules."),
    ("Large language model (LLM)", "A model trained on large amounts of text to predict and generate language."),
    ("Generative AI", "AI that creates new text, images, audio, video or code from learned patterns."),
    ("Natural language processing (NLP)", "Methods that help computers analyse, understand and generate human language."),
    ("Computer vision", "AI techniques used to interpret images and video."),
    ("Predictive analytics", "Using historical data and models to estimate what is likely to happen next."),
    ("AI agent", "A system that can plan and take a sequence of actions towards a goal, often using tools."),
    ("Human in the loop", "A workflow where a person reviews, approves or corrects important AI decisions."),
    ("Model drift", "A decline in model performance when real-world data or behaviour changes after deployment."),
    ("Explainability", "The ability to give people a useful account of why an AI system produced a result."),
    ("Algorithmic bias", "Systematic unfairness caused by data, design choices, objectives or how a system is used."),
]

def wrap(text, c, font, size, width):
    words=text.split(); lines=[]; cur=""
    for word in words:
        trial=(cur+" "+word).strip()
        if c.stringWidth(trial,font,size) <= width: cur=trial
        else:
            if cur: lines.append(cur)
            cur=word
    if cur: lines.append(cur)
    return lines

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    w,h=A4; m=42
    c=canvas.Canvas(str(OUT), pagesize=A4, pageCompression=1, invariant=1)
    c.setTitle("AI Edge - Plain-English AI Glossary Cheat Sheet")
    c.setAuthor("Jonathan Harris")
    c.setFillColor(HexColor("#0D1420")); c.rect(0,h-112,w,112,fill=1,stroke=0)
    c.setFillColor(HexColor("#FFFFFF")); c.setFont("Helvetica-Bold",20); c.drawString(m,h-52,"AI Edge: AI Glossary Cheat Sheet")
    c.setFont("Helvetica",10.5); c.setFillColor(HexColor("#DBEAFE")); c.drawString(m,h-73,"12 useful AI terms in plain English - signal, not acronym soup.")
    c.setFillColor(HexColor("#93C5FD")); c.setFont("Helvetica-Bold",9.5); c.drawString(m,h-94,"jonathan-harris.online/glossary/")
    y=h-137; col_gap=24; col_w=(w-2*m-col_gap)/2
    for i,(term,desc) in enumerate(TERMS):
        if i==6: y=h-137
        x=m if i<6 else m+col_w+col_gap
        c.setFillColor(HexColor("#111827")); c.setFont("Helvetica-Bold",9.4); c.drawString(x,y,term)
        y-=12
        c.setFillColor(HexColor("#374151")); c.setFont("Helvetica",8.5)
        for line in wrap(desc,c,"Helvetica",8.5,col_w):
            c.drawString(x,y,line); y-=10.2
        y-=7
    box_y=46
    c.setFillColor(HexColor("#EFF6FF")); c.roundRect(m,box_y,w-2*m,52,8,fill=1,stroke=0)
    c.setFillColor(HexColor("#1E3A8A")); c.setFont("Helvetica-Bold",9.5); c.drawString(m+12,box_y+34,"Useful rule of thumb")
    c.setFillColor(HexColor("#1F2937")); c.setFont("Helvetica",8.7)
    rule="Ask what data the system uses, what decision it influences, who checks it, and what happens when it is wrong."
    for n,line in enumerate(wrap(rule,c,"Helvetica",8.7,w-2*m-24)):
        c.drawString(m+12,box_y+19-n*10,line)
    c.setFillColor(HexColor("#6B7280")); c.setFont("Helvetica",7.5); c.drawRightString(w-m,24,"AI Edge by Jonathan Harris | 2026")
    c.save()
    print(OUT)
if __name__ == '__main__': main()
