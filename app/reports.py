from html import escape
from pathlib import Path
from weasyprint import HTML
from .settings import settings

def report(p,v):
    rows=''.join('<tr>'+''.join('<td>'+escape(str(i.get(k,'')))+'</td>' for k in ['severity','category','location','observed_problem','expected_requirement','evidence','suggested_correction','confidence'])+'</tr>' for i in v.result.get('issues',[]))
    checks=''.join('<li>'+escape(str(c))+'</li>' for c in v.result.get('checks',[]))
    html='<!doctype html><meta charset="utf-8"><style>body{font:11px sans-serif;color:#173456}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccd;padding:5px;overflow-wrap:anywhere}@page{size:A4 landscape;margin:15mm}</style><h1>PaperFlow AI · Correction report</h1><h2>'+escape(p.title or p.id)+'</h2><p>Paper '+escape(p.id)+' · Version '+str(v.number)+'</p><p>This report is evidence for editorial review, not publisher certification.</p><table><tr><th>Severity</th><th>Category</th><th>Location</th><th>Observed</th><th>Expected</th><th>Evidence</th><th>Suggestion</th><th>Confidence</th></tr>'+rows+'</table><h2>Check coverage</h2><ul>'+checks+'</ul>'
    target=settings.storage/(v.id+'.report.html');target.write_text(html)
    pdf=target.with_suffix('.pdf');HTML(string=html).write_pdf(pdf)
    return target,pdf
