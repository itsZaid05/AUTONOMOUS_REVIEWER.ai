"""Five source/revision pairs with genuine formatting, compilation, writing and metadata defects."""
import io,json,zipfile
from pathlib import Path
from docx import Document
from docx.shared import Pt,Mm

def manuscript(number,revised=False):
    title=f'Controlled Proceedings Study {number}'
    if number==3:
        body='\\documentclass[a4paper]{llncs}\n\\title{'+title+'}\n\\author{Author 3}\n\\institute{Controlled Demo University}\n\\begin{document}\n\\maketitle\nAbstract\n\nA reproducible experiment in conference automation.\n\nKeywords: testing, proceedings\n\nIntroduction\n\n'
        body+=('An undefined reference \\ref{missing}.\\missingcommand' if not revised else 'A resolved reference \\ref{method}.\\section{Method}\\label{method} The method is reproducible.')
        body+='\n\nReferences\n\nA test bibliography.\n\\end{document}'
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('main.tex',body)
        return 'paper.zip',out.getvalue()
    d=Document();d.styles['Normal'].font.name='Times New Roman';d.styles['Normal'].font.size=Pt(10)
    sec=d.sections[0];sec.page_width=Mm(210);sec.page_height=Mm(297);sec.left_margin=sec.right_margin=Mm(44);sec.top_margin=sec.bottom_margin=Mm(52)
    d.add_paragraph(title,'Title');d.add_paragraph('Authors: Author '+str(number));
    if number!=4 or revised:d.add_paragraph('Affiliation: Controlled Demo University')
    d.add_paragraph(f'Email: author{number}@example.test');d.add_paragraph('Abstract')
    sentence='The reproducible experiment evaluates conference automation.'
    if number in [4,5] and not revised:sentence='The the reproducible experiment evaluates conference automation.'
    p=d.add_paragraph(sentence)
    if number==2 and not revised:
        p.runs[0].font.size=Pt(18);sec.page_width=Mm(216)
    d.add_paragraph('Keywords: testing, proceedings');d.add_heading('Introduction',1);d.add_paragraph('A controlled demonstration manuscript.');d.add_heading('References',1);d.add_paragraph('A test bibliography.')
    out=io.BytesIO();d.save(out);return 'paper.docx',out.getvalue()

def place(root,number,revised=False,token=None):
    name,content=manuscript(number,revised)
    folder=root/(f'paper-{number}'+('-revision' if revised else ''));folder.mkdir(parents=True,exist_ok=True)
    (folder/name).write_bytes(content)
    metadata={'title':f'Controlled Proceedings Study {number}','authors':f'Author {number}','email':f'author{number}@example.test'}
    if number!=4 or revised:metadata['affiliation']='Controlled Demo University'
    manifest={'paper_key':f'paper-{number}','source':name,'metadata':metadata}
    if token:manifest['revision_token']=token
    # Manifest is the atomic ready marker; source files are written first.
    temporary=folder/'submission.tmp';temporary.write_text(json.dumps(manifest,indent=2));temporary.replace(folder/'submission.json')
