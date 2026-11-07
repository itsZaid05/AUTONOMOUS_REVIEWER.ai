import csv,io,json,uuid,zipfile
from pathlib import Path
from html import escape
from pydantic import BaseModel
from fastapi import Depends,HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from docx import Document
from docx.shared import Mm,Pt
from docx.oxml import OxmlElement
from pypdf import PdfWriter
from weasyprint import HTML
from .main import app,admin,record
from .db import Session,Paper,Version,Audit
from .settings import settings
class PublicationRequest(BaseModel):
    conference:str
    information:str=''
    paper_ids:list[str]
    confirm_editorial_approval:bool=False
@app.post('/publications',dependencies=[Depends(admin)])
def publish(body:PublicationRequest):
    if not body.confirm_editorial_approval or not body.paper_ids:raise HTTPException(400,'Select papers and confirm editorial approval')
    if len(body.paper_ids)>1000 or len(set(body.paper_ids))!=len(body.paper_ids):raise HTTPException(400,'Invalid paper selection')
    with Session() as s:
        papers=[]
        for pid in body.paper_ids:
            p=s.get(Paper,pid,with_for_update=True)
            if not p or p.status!='Approved' or p.approved_version!=p.latest:raise HTTPException(409,'All selected papers must have current editor-approved versions')
            v=s.scalar(select(Version).where(Version.paper_id==pid,Version.number==p.approved_version))
            if not p.title or not p.authors:raise HTTPException(409,'Editor must supply title and authors for every paper')
            document=v.result['document'];pdf=document.get('rendered_pdf')
            if not pdf or not Path(pdf).exists():raise HTTPException(409,'Approved manuscript PDF missing')
            # Abstract/keywords come from editor-reviewed manuscript text; no AI rewriting.
            import re
            text=document['text']
            abstract=re.search(r'\bAbstract\s*[:—.-]?\s*(.*?)(?=\bKeywords\b|\bIndex Terms\b|\n\s*(?:1[. ]+)?Introduction\b|\Z)',text,re.I|re.S)
            keywords=re.search(r'\b(?:Keywords|Index Terms)\s*[:—.-]?\s*([^\n]+)',text,re.I)
            papers.append((p,v,abstract.group(1).strip() if abstract else 'Abstract could not be extracted; editor review required.',keywords.group(1).strip() if keywords else ''))
        papers.sort(key=lambda x:(x[0].track,x[0].title))
        pubid=uuid.uuid4().hex;out=settings.storage/'publications'/pubid;out.mkdir(parents=True)
        doc=Document();section=doc.sections[0];section.page_width=Mm(210);section.page_height=Mm(297);section.left_margin=section.right_margin=Mm(44);section.top_margin=section.bottom_margin=Mm(52);doc.styles['Normal'].font.name='Times New Roman';doc.styles['Normal'].font.size=Pt(10)
        page_field=OxmlElement('w:fldSimple');page_field.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}instr','PAGE');section.footer.paragraphs[0]._p.append(page_field)
        doc.add_heading(body.conference,0);doc.add_paragraph(body.information);doc.add_heading('Book of Abstracts',0);doc.add_page_break();doc.add_heading('Contents',1)
        for p,v,a,k in papers:doc.add_paragraph(p.title+' · '+p.authors)
        html='<html><meta charset="utf-8"><style>@page{size:A4;margin:52mm 44mm;@bottom-center{content:counter(page)}}body{font:11pt serif;color:#173456}article{break-before:page}h1{font:24pt sans-serif}h2{font:17pt sans-serif}</style><h1>'+escape(body.conference)+'</h1><p>'+escape(body.information)+'</p><h2>Book of Abstracts</h2><article><h2>Contents</h2><ol>'+''.join('<li>'+escape(p.title)+'</li>' for p,_,_,_ in papers)+'</ol></article>'
        writer=PdfWriter();manifest=[];metadata=io.StringIO();cw=csv.writer(metadata);cw.writerow(['paper_id','version','title','authors','affiliation','track','keywords','abstract'])
        with zipfile.ZipFile(out/'camera-ready-sources.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p,v,abstract,keywords in papers:
                doc.add_page_break();doc.add_heading(p.track,1);doc.add_heading(p.title,2);doc.add_paragraph(p.authors);doc.add_paragraph(p.affiliation);doc.add_heading('Abstract',3);doc.add_paragraph(abstract);doc.add_paragraph('Keywords: '+keywords)
                html+='<article><p>'+escape(p.track)+'</p><h2>'+escape(p.title)+'</h2><p>'+escape(p.authors)+'</p><p>'+escape(p.affiliation)+'</p><h3>Abstract</h3><p>'+escape(abstract)+'</p><p>Keywords: '+escape(keywords)+'</p></article>'
                pdf=Path(v.result['document']['rendered_pdf']);writer.append(str(pdf));(out/(p.id+'.pdf')).write_bytes(pdf.read_bytes());z.write(v.path,p.id+'/'+v.filename)
                cw.writerow([p.id,v.number,p.title,p.authors,p.affiliation,p.track,keywords,abstract]);manifest.append({'paper_id':p.id,'version':v.number,'sha256':v.digest,'issues':v.result['issues'],'checks':v.result['checks']})
                record(s,p.id,'publication_included',{'publication':pubid,'version':v.number})
        doc.add_page_break();doc.add_heading('Author index',1)
        for author in sorted(set(a.strip() for p,_,_,_ in papers for a in p.authors.split(';') if a.strip())):doc.add_paragraph(author+': '+', '.join(p.title for p,_,_,_ in papers if author in [a.strip() for a in p.authors.split(';')]))
        html+='<article><h2>Author index</h2>'+''.join('<p>'+escape(a)+': '+escape(', '.join(p.title for p,_,_,_ in papers if a in [author.strip() for author in p.authors.split(';')]))+'</p>' for a in sorted(set(a.strip() for p,_,_,_ in papers for a in p.authors.split(';') if a.strip())))+'</article></html>'
        doc.save(out/'book-of-abstracts.docx');HTML(string=html).write_pdf(out/'book-of-abstracts.pdf');writer.write(out/'proceedings.pdf');writer.close()
        (out/'metadata.csv').write_text(metadata.getvalue());(out/'audit.json').write_text(json.dumps({'conference':body.conference,'papers':manifest},indent=2,default=str))
        (out/'book-of-abstracts.html').write_text(html)
        s.commit()
        return {'publication_id':pubid,'files':sorted(p.name for p in out.iterdir())}
@app.get('/publications/{pubid}/{filename}',dependencies=[Depends(admin)])
def export(pubid:str,filename:str):
    import re
    if not re.fullmatch('[a-f0-9]{32}',pubid) or Path(filename).name!=filename:raise HTTPException(400)
    p=settings.storage/'publications'/pubid/filename
    if not p.is_file():raise HTTPException(404)
    return FileResponse(p,filename=filename)
class MetadataEdit(BaseModel):
    title:str
    authors:str
    affiliation:str=''
    email:str=''
    track:str='General'
@app.patch('/papers/{pid}',dependencies=[Depends(admin)])
def metadata_edit(pid:str,body:MetadataEdit):
    with Session() as s:
        p=s.get(Paper,pid,with_for_update=True)
        if not p:raise HTTPException(404)
        for k,v in body.model_dump().items():setattr(p,k,v)
        p.approved_version=None;p.status='Under Review';record(s,pid,'metadata_updated',body.model_dump());s.commit()
    return {'updated':pid,'approval_invalidated':True}
