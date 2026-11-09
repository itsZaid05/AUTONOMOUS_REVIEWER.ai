import csv,io,json,uuid,zipfile,subprocess,tempfile,shutil
from pathlib import Path
from html import escape
from pydantic import BaseModel
from fastapi import Depends,HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from docx import Document
from docx.shared import Mm,Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from pypdf import PdfWriter
from weasyprint import HTML
from .main import app,admin,record
from .db import Session,Paper,Version,Audit,Enrollment,Conference
from .settings import settings
def page_reference(paragraph,bookmark):
    field=OxmlElement('w:fldSimple');field.set(qn('w:instr'),'PAGEREF '+bookmark+r' \h')
    paragraph._p.append(field)
def bookmark(paragraph,name,index):
    start=OxmlElement('w:bookmarkStart');start.set(qn('w:id'),str(index));start.set(qn('w:name'),name)
    end=OxmlElement('w:bookmarkEnd');end.set(qn('w:id'),str(index))
    paragraph._p.insert(0,start);paragraph._p.append(end)
def finalize_docx(path,papers):
    """Resolve Word PAGEREF fields with Writer and verify them against its rendered pages."""
    from lxml import etree
    from pypdf import PdfReader
    with tempfile.TemporaryDirectory() as directory:
        work=Path(directory)
        command=['soffice','-env:UserInstallation='+work.as_uri()+'/profile','--headless','--convert-to','docx','--outdir',str(work),str(path.resolve())]
        completed=subprocess.run(command,capture_output=True,timeout=90)
        updated=work/path.name
        if completed.returncode or not updated.exists():raise RuntimeError('Book DOCX field update failed')
        rendered=subprocess.run(['soffice','-env:UserInstallation='+work.as_uri()+'/pdf-profile','--headless','--convert-to','pdf','--outdir',str(work),str(updated)],capture_output=True,timeout=90)
        pdf=updated.with_suffix('.pdf')
        if rendered.returncode or not pdf.exists():raise RuntimeError('Book DOCX pagination verification failed')
        with zipfile.ZipFile(updated) as archive:tree=etree.fromstring(archive.read('word/document.xml'))
        reader=PdfReader(pdf);pages={};namespace={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        for paper,_,_,_ in papers:
            fields=tree.xpath('//w:p[w:r/w:instrText[contains(., $target)]]',namespaces=namespace,target='PAGEREF paper_'+paper.id)
            if len(fields)<2:raise RuntimeError('Book contents/index page reference missing')
            # PAGEREF cached result is in the field run, following its separator.
            values=[]
            for paragraph in fields:
                capture=False
                for node in paragraph.iter():
                    if node.tag==qn('w:fldChar'):
                        kind=node.get(qn('w:fldCharType'))
                        if kind=='separate':capture=True
                        elif kind=='end':capture=False
                    elif capture and node.tag==qn('w:t') and node.text and node.text.isdecimal():values.append(int(node.text))
            if len(values)<2 or len(set(values))!=1:raise RuntimeError('Book has unresolved/inconsistent page fields')
            page=values[0]
            if page<1 or page>len(reader.pages) or ' '.join(paper.title.split()) not in ' '.join(reader.pages[page-1].extract_text().split()):raise RuntimeError('Book DOCX page reference does not match rendered title')
            pages[paper.id]=page
        shutil.copyfile(updated,path);shutil.copyfile(pdf,path.with_name('book-of-abstracts-docx.pdf'))
        return pages

class PublicationRequest(BaseModel):
    conference:str
    information:str=''
    paper_ids:list[str]
    confirm_editorial_approval:bool=False
def build(body:PublicationRequest,draft=False):
    if (not draft and not body.confirm_editorial_approval) or not body.paper_ids:raise HTTPException(400,'Select papers and confirm editorial approval')
    if len(body.paper_ids)>1000 or len(set(body.paper_ids))!=len(body.paper_ids):raise HTTPException(400,'Invalid paper selection')
    with Session() as s:
        papers=[]
        for pid in body.paper_ids:
            p=s.get(Paper,pid,with_for_update=True)
            if not p or (not draft and (p.status!='Approved' or p.approved_version!=p.latest)) or (draft and p.status not in ['Publication Ready','Approved']):raise HTTPException(409,'All selected papers must have current editor-approved versions')
            v=s.scalar(select(Version).where(Version.paper_id==pid,Version.number==p.latest))
            if not p.title or not p.authors or not p.affiliation:raise HTTPException(409,'Editor must supply title and authors for every paper')
            enrollment=s.scalar(select(Enrollment).where(Enrollment.paper_id==pid))
            if enrollment:
                policy=s.get(Conference,enrollment.conference_id).config
                if policy.get('real_paper_mode'):
                    if enrollment.state!='Publication Ready' or enrollment.handled_version!=p.latest:raise HTTPException(409,'Current conference validation and editorial decisions are required')
                    if not draft and not policy.get('publication_authorized'):raise HTTPException(409,'Final conference publication authorization is required')
                    ai=next((c for c in v.result.get('checks',[]) if c.get('check')=='AI proofreading'),{})
                    if ai.get('provider')!='gemini' or ai.get('status')!='completed' or ai.get('coverage_ratio')!=1:raise HTTPException(409,'Successful whole-document Gemini review is required')
            document=v.result['document'];pdf=document.get('rendered_pdf')
            if not pdf or not Path(pdf).exists():raise HTTPException(409,'Approved manuscript PDF missing')
            verified=document.get('verified_metadata') or {}
            if not verified or any(not verified.get(k) for k in ['title','authors','affiliation','abstract','keywords']):raise HTTPException(409,'Complete verified metadata is required for publication')
            if any(verified[k]!=getattr(p,k) for k in ['title','authors','affiliation']):raise HTTPException(409,'Verified metadata is stale; verify the current version again')
            abstract=verified.get('abstract','')
            keywords=verified.get('keywords','')
            if not abstract or not keywords:raise HTTPException(409,'Abstract and keywords must be extracted and verified; no placeholder is permitted')
            papers.append((p,v,abstract,keywords))
        papers.sort(key=lambda x:(x[0].track,x[0].title))
        pubid=uuid.uuid4().hex;out=settings.storage/'publications'/pubid;out.mkdir(parents=True)
        doc=Document();section=doc.sections[0];section.page_width=Mm(210);section.page_height=Mm(297);section.left_margin=section.right_margin=Mm(44);section.top_margin=section.bottom_margin=Mm(52);doc.styles['Normal'].font.name='Times New Roman';doc.styles['Normal'].font.size=Pt(10)
        page_field=OxmlElement('w:fldSimple');page_field.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}instr','PAGE');section.footer.paragraphs[0]._p.append(page_field)
        doc.add_heading(body.conference,0);doc.add_paragraph(body.information);doc.add_heading('Draft Book of Abstracts' if draft else 'Book of Abstracts',0);doc.add_page_break();doc.add_heading('Contents',1)
        update=OxmlElement('w:updateFields');update.set(qn('w:val'),'true');doc.settings.element.append(update)
        for p,v,a,k in papers:
            paragraph=doc.add_paragraph(p.title+' · '+p.authors+' … ');page_reference(paragraph,'paper_'+p.id)
        html='<html><meta charset="utf-8"><style>@page{size:A4;margin:52mm 44mm;@bottom-center{content:counter(page)}}body{font:11pt serif;color:#173456}article{break-before:page}h1{font:24pt sans-serif}h2{font:17pt sans-serif}.toc a{color:inherit;text-decoration:none}.toc a::after,.author a::after{content:leader(dotted) target-counter(attr(href),page)}</style><h1>'+escape(body.conference)+'</h1><p>'+escape(body.information)+'</p><h2>'+('DRAFT — Book of Abstracts' if draft else 'Book of Abstracts')+'</h2><article><h2>Contents</h2><ol>'+''.join('<li class="toc"><a href="#paper_'+p.id+'">'+escape(p.title)+'</a></li>' for p,_,_,_ in papers)+'</ol></article>'
        writer=PdfWriter();manifest=[];metadata=io.StringIO();cw=csv.writer(metadata);cw.writerow(['paper_id','version','title','authors','affiliation','track','keywords','abstract'])
        with zipfile.ZipFile(out/'camera-ready-sources.zip','w',zipfile.ZIP_DEFLATED) as z:
            for p,v,abstract,keywords in papers:
                doc.add_page_break();doc.add_heading(p.track,1);bookmark(doc.add_heading(p.title,2),'paper_'+p.id,len(manifest)+1);doc.add_paragraph(p.authors);doc.add_paragraph(p.affiliation);doc.add_heading('Abstract',3);doc.add_paragraph(abstract);doc.add_paragraph('Keywords: '+keywords)
                html+='<article id="paper_'+p.id+'"><p>'+escape(p.track)+'</p><h2>'+escape(p.title)+'</h2><p>'+escape(p.authors)+'</p><p>'+escape(p.affiliation)+'</p><h3>Abstract</h3><p>'+escape(abstract)+'</p><p>Keywords: '+escape(keywords)+'</p></article>'
                pdf=Path(v.result['document']['rendered_pdf']);writer.append(str(pdf));(out/(p.id+'.pdf')).write_bytes(pdf.read_bytes());z.write(v.path,p.id+'/'+v.filename)
                cw.writerow([p.id,v.number,p.title,p.authors,p.affiliation,p.track,keywords,abstract]);manifest.append({'paper_id':p.id,'version':v.number,'title':p.title,'authors':p.authors,'affiliation':p.affiliation,'keywords':keywords,'track':p.track,'abstract':abstract,'metadata_verified':bool(v.result['document'].get('verified_metadata')),'sha256':v.digest,'issues':v.result['issues'],'checks':v.result['checks']})
                record(s,p.id,'publication_included',{'publication':pubid,'version':v.number})
        doc.add_page_break();doc.add_heading('Author index',1)
        authors=sorted(set(a.strip() for p,_,_,_ in papers for a in p.authors.split(';') if a.strip()))
        html+='<article><h2>Author index</h2>'
        for author in authors:
            paragraph=doc.add_paragraph(author+': ');links=[]
            for p,_,_,_ in papers:
                if author not in [a.strip() for a in p.authors.split(';')]:continue
                paragraph.add_run(p.title+' … ');page_reference(paragraph,'paper_'+p.id);paragraph.add_run('; ')
                links.append('<a href="#paper_'+p.id+'">'+escape(p.title)+'</a>')
            html+='<p class="author">'+escape(author)+': '+'; '.join(links)+'</p>'
        html+='</article></html>'
        doc.save(out/'book-of-abstracts.docx')
        word_pages=finalize_docx(out/'book-of-abstracts.docx',papers)
        rendered=HTML(string=html).render()
        pdf_pages={p.id:index+1 for index,page in enumerate(rendered.pages) for p,_,_,_ in papers if 'paper_'+p.id in page.anchors}
        if len(pdf_pages)!=len(papers):raise RuntimeError('Book PDF contents anchors missing')
        rendered.write_pdf(out/'book-of-abstracts.pdf')
        (out/'pagination.json').write_text(json.dumps({'pdf':pdf_pages,'docx':word_pages,'docx_verified_against':'book-of-abstracts-docx.pdf'},indent=2))
        writer.write(out/'proceedings.pdf');writer.close()
        (out/'metadata.csv').write_text(metadata.getvalue());(out/'audit.json').write_text(json.dumps({'conference':body.conference,'draft':draft,'papers':manifest},indent=2,default=str))
        (out/'book-of-abstracts.html').write_text(html)
        s.commit()
        return {'publication_id':pubid,'draft':draft,'included':[{'paper_id':p.id,'version':v.number} for p,v,_,_ in papers],'files':sorted(p.name for p in out.iterdir())}
@app.post('/publications',dependencies=[Depends(admin)])
def publish(body:PublicationRequest):return build(body,draft=False)

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
