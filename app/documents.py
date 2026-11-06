import io,os,re,stat,subprocess,tempfile,zipfile,shutil,uuid
from pathlib import Path
import pymupdf
from docx import Document
MAX_EXPANDED=100*1024*1024

def safe_zip(path,target):
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        if len(infos)>1000 or sum(i.file_size for i in infos)>MAX_EXPANDED: raise ValueError('ZIP expansion limit exceeded')
        for i in infos:
            p=Path(i.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in i.filename or stat.S_ISLNK(i.external_attr>>16): raise ValueError('Unsafe ZIP member')
            if i.flag_bits&1:raise ValueError('Encrypted ZIP not supported')
            if not i.is_dir():
                dest=target/p;dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(i) as src,dest.open('wb') as out:
                    shutil.copyfileobj(src,out)

def pdf_info(path):
    with pymupdf.open(path) as pdf:
        if pdf.is_encrypted:raise ValueError('Password-protected PDF')
        if len(pdf)>500:raise ValueError('PDF page limit exceeded')
        pages=[]
        for i,p in enumerate(pdf):
            spans=[s for b in p.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
            pages.append({'number':i+1,'width_mm':round(p.rect.width*25.4/72,2),'height_mm':round(p.rect.height*25.4/72,2),'text':p.get_text()[:100000],'fonts':sorted(set(s['font'] for s in spans)),'font_sizes':sorted(set(round(s['size'],1) for s in spans)),'text_bounds':[round(x*25.4/72,2) for x in p.get_text('blocks')[0][:4]] if p.get_text('blocks') else None})
        return pages

def inspect_document(path):
    source=Path(path);result={'format':source.suffix[1:],'pages':[],'text':'','rendered_pdf':None,'notes':[]}
    with tempfile.TemporaryDirectory() as td:
        work=Path(td)
        if source.suffix=='.pdf':
            result['pages']=pdf_info(source);result['rendered_pdf']=str(source)
        elif source.suffix=='.docx':
            with zipfile.ZipFile(source) as z:
                if sum(i.file_size for i in z.infolist())>MAX_EXPANDED:raise ValueError('DOCX expansion limit exceeded')
            doc=Document(source)
            result['text']='\n'.join(p.text for p in doc.paragraphs)+'\n'+'\n'.join(c.text for t in doc.tables for r in t.rows for c in r.cells)
            result['paragraphs']=[{'index':i+1,'text':p.text,'style':p.style.name,'space_before_pt':p.paragraph_format.space_before.pt if p.paragraph_format.space_before else None,'space_after_pt':p.paragraph_format.space_after.pt if p.paragraph_format.space_after else None,'runs':[{'font':r.font.name,'size_pt':r.font.size.pt if r.font.size else None} for r in p.runs if r.text.strip()]} for i,p in enumerate(doc.paragraphs)]
            result['sections']=[{'width_mm':round(s.page_width.mm,2),'height_mm':round(s.page_height.mm,2),'top_mm':round(s.top_margin.mm,2),'bottom_mm':round(s.bottom_margin.mm,2),'left_mm':round(s.left_margin.mm,2),'right_mm':round(s.right_margin.mm,2),'columns':s._sectPr.xpath('./w:cols')[0].get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}num','1') if s._sectPr.xpath('./w:cols') else '1'} for s in doc.sections]
            try:
                proc=subprocess.run(['soffice','-env:UserInstallation=file://'+td+'/lo-profile','--headless','--convert-to','pdf','--outdir',td,str(source)],capture_output=True,timeout=90)
                rendered=work/(source.stem+'.pdf')
                if proc.returncode or not rendered.exists():raise RuntimeError('LibreOffice did not produce PDF')
                target=source.with_suffix('.rendered.pdf');shutil.copyfile(rendered,target)
                result['rendered_pdf']=str(target);result['pages']=pdf_info(target)
            except (OSError,subprocess.TimeoutExpired,RuntimeError) as e:result['notes'].append('DOCX rendering unavailable: '+str(e))
        else:
            if source.suffix=='.zip': safe_zip(source,work)
            else:shutil.copyfile(source,work/'main.tex')
            mains=[p for p in work.rglob('*.tex') if '\\documentclass' in p.read_text(errors='replace')]
            if len(mains)!=1:raise ValueError('LaTeX project must have exactly one documentclass entry point')
            main=mains[0]
            result['source_text']=main.read_text(errors='replace')[:500000]
            # No network, no shell escape, no host secrets, no host writable mount outside project.
            container='paperflow-tex-'+uuid.uuid4().hex
            cmd=['docker','run','--name',container,'--ulimit','cpu=45:45','--ulimit','fsize=52428800:52428800','--rm','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=64','--memory=512m','--cpus=1','--user',f'{os.getuid()}:{os.getgid()}','--tmpfs','/tmp:rw,noexec,nosuid,size=64m','-v',f'{work}:/work:rw','-w','/work/'+str(main.parent.relative_to(work)),'paperflow-tex:local','pdflatex','-no-shell-escape','-interaction=nonstopmode','-halt-on-error',main.name]
            try:
                p=subprocess.run(cmd,capture_output=True,timeout=60)
                if p.returncode:raise ValueError('Isolated LaTeX compilation failed: '+p.stdout.decode(errors='replace')[-1800:])
                target=source.with_suffix('.rendered.pdf');shutil.copyfile(main.with_suffix('.pdf'),target)
                result['rendered_pdf']=str(target);result['pages']=pdf_info(target)
            except subprocess.TimeoutExpired:raise ValueError('LaTeX compilation exceeded 60 seconds')
            finally:subprocess.run(['docker','rm','-f',container],capture_output=True,timeout=15)
        if not result['text']:result['text']='\n'.join(p['text'] for p in result['pages'])
        result['notes'].append('Reading order, equations, figure quality, semantic accuracy, and citation style require editorial review.')
    return result
