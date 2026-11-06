"""Generate mixed-format manuscripts with intentional, documented repeated-word errors."""
from pathlib import Path
import io,zipfile
from docx import Document
import pymupdf
root=Path('data/samples');root.mkdir(parents=True,exist_ok=True)
for i in range(10):
    text=f'Sample Research {i}\nAuthor {i}\nAbstract\nThe the experiment {i} evaluates a reproducible workflow.\nKeywords: testing, publishing\nIntroduction\nA controlled sample.\nReferences\nEditorial verification required.'
    if i%3==0:
        d=Document()
        for line in text.splitlines():d.add_paragraph(line)
        d.save(root/f'paper-{i}.docx')
    elif i%3==1:
        pdf=pymupdf.open();page=pdf.new_page();page.insert_textbox(pymupdf.Rect(60,60,530,780),text,fontsize=11);pdf.save(root/f'paper-{i}.pdf');pdf.close()
    else:
        tex='\\documentclass{article}\n\\begin{document}\n'+text.replace('\n','\n\n')+'\n\\end{document}'
        with zipfile.ZipFile(root/f'paper-{i}.zip','w') as z:z.writestr('main.tex',tex)
print('Generated 10 manuscripts: 4 DOCX, 3 PDF, 3 LaTeX ZIP')
