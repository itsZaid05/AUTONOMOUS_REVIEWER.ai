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
            pages.append({'number':i+1,'width_mm':round(p.rect.width*25.4/72,2),'height_mm':round(p.rect.height*25.4/72,2),'text':p.get_text(),'fonts':sorted(set(s['font'] for s in spans)),'font_sizes':sorted(set(round(s['size'],1) for s in spans)),'text_bounds':[round(x*25.4/72,2) for x in p.get_text('blocks')[0][:4]] if p.get_text('blocks') else None})
        return pages

def effective(run,paragraph,doc,property):
    value=getattr(run.font,property)
    if value is not None:return value
    for initial in [run.style,paragraph.style,doc.styles['Normal']]:
        visited=set();style=initial
        while style is not None and style.style_id not in visited:
            visited.add(style.style_id);value=getattr(style.font,property)
            if value is not None:return value
            style=style.base_style
    return None

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
            from lxml import etree
            W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            texts=[]
            for part in doc.part.package.parts:
                name=str(part.partname)
                if name=='/word/document.xml' or re.fullmatch(r'/word/(?:footnotes|endnotes|header[0-9]+|footer[0-9]+)\.xml',name):
                    tree=etree.fromstring(part.blob,parser=etree.XMLParser(resolve_entities=False,no_network=True))
                    for paragraph in tree.iter(W+'p'):
                        words=[]
                        for node in paragraph.iter(W+'t'):
                            ancestor=node.getparent()
                            while ancestor is not None and ancestor.tag!=W+'p':ancestor=ancestor.getparent()
                            if ancestor is paragraph:words.append(node.text or '')
                        if words:texts.append(''.join(words))
            result['text']='\n'.join(texts)
            result['extraction']={'method':'DOCX body, tables, text boxes, notes, headers and footers XML','paragraphs':len(texts),'truncated':False}
            result['paragraphs']=[]
            for i,p in enumerate(doc.paragraphs):
                runs=[]
                for r in p.runs:
                    if not r.text.strip():continue
                    size=effective(r,p,doc,'size')
                    runs.append({'font':effective(r,p,doc,'name'),'size_pt':size.pt if size else None,'bold':effective(r,p,doc,'bold'),'italic':effective(r,p,doc,'italic')})
                result['paragraphs'].append({'index':i+1,'text':p.text,'style':p.style.name,'space_before_pt':p.paragraph_format.space_before.pt if p.paragraph_format.space_before is not None else None,'space_after_pt':p.paragraph_format.space_after.pt if p.paragraph_format.space_after is not None else None,'has_image':bool(p._p.xpath('.//w:drawing')),'runs':runs})
            result['tables']=[]
            for i,t in enumerate(doc.tables):
                preceding=t._tbl.getprevious();text=''.join(preceding.itertext()) if preceding is not None else ''
                result['tables'].append({'number':i+1,'preceding_text':text})
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
            result['bibliography_ids']=sorted(set(key for file in work.rglob('*.bib') for key in re.findall(r'@\w+\s*\{\s*([^,\s]+)',file.read_text(errors='replace'))))
            result['source_text']='\n'.join(p.read_text(errors='replace') for p in work.rglob('*.tex'))
            from .compile_client import compile_source
            target,compiled=compile_source(source)
            result['rendered_pdf']=str(target);result['pages']=pdf_info(target)
            result['compilation']=compiled
            for dimension in ['text_width_mm','text_height_mm']:
                if dimension in compiled:result[dimension]=compiled[dimension]
            result['latex_warnings']=compiled.get('warnings',[])
        if not result['text']:result['text']='\n'.join(p['text'] for p in result['pages'])
        txt=result['text']
        abstract=re.search(r'\bAbstract\s*[:.—-]?\s*(.*?)(?=\bKeywords\b|\bIndex Terms\b|\n\s*Introduction\b|\Z)',txt,re.I|re.S)
        keywords=re.search(r'\b(?:Keywords|Index Terms)\s*[:.—-]?\s*([^\n]+)',txt,re.I)
        result['metadata']={'abstract':abstract.group(1).strip() if abstract else '', 'keywords':keywords.group(1).strip() if keywords else ''}
        if result.get('source_text'):
            labels=set(re.findall(r'\\label\{([^}]+)\}',result['source_text']))
            refs=set(re.findall(r'\\(?:ref|eqref)\{([^}]+)\}',result['source_text']))
            result['unresolved_references']=sorted(refs-labels)
        result['notes'].append('Reading order, equations, figure quality, semantic accuracy, and citation style require editorial review.')
    return result
