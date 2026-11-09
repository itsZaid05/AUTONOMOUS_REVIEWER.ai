"""Checks grounded in the retained LLNCS class; uncertain extraction is never a verified error."""
import hashlib,re
SOURCE='Springer LLNCS 2.22: llncs.cls (retained TeX Live publisher package)'

def check(doc,pid,profile):
    issues=[];checks=[]
    def finding(rule,location,problem,expected,evidence,fix,severity='error',method='DOCX XML / effective styles'):
        catalog={'rule_id':rule,'source':SOURCE,'template_version':'2.22','expected_value':expected,'tolerance':.2,'severity':severity,'validation_method':method,'applicability':doc['format']}
        issues.append({'paper_id':pid,'category':rule.split('.')[1],'severity':severity,'location':location,'observed_problem':problem,'expected_requirement':expected,'evidence':str(evidence),'suggested_correction':fix,'confidence':1 if severity=='error' else .75,'verification_status':'Verified Error' if severity=='error' else 'Requires Human Review','rule':catalog,'rule_source':SOURCE,'fingerprint':hashlib.sha256((rule+location+problem).encode()).hexdigest()[:16]})
    if 'LNCS' not in profile.get('name','').upper():return issues,checks
    paragraphs=doc.get('paragraphs',[])
    for p in paragraphs:
        loc=f"paragraph {p['index']}"
        heading=re.fullmatch(r'Heading ([12])',p['style'])
        if heading:
            expected=12 if heading[1]=='1' else 10
            for run in p['runs']:
                if run['size_pt'] is not None and abs(run['size_pt']-expected)>.2:finding('LNCS.headings.size',loc,'Heading font size differs from the class',f'{expected} pt',run['size_pt'],'Apply the configured LNCS heading size')
                if run.get('bold') is False:finding('LNCS.headings.weight',loc,'Heading is explicitly not bold','Bold heading',p['text'],'Apply bold formatting as defined by the class')
        if p['style']=='Normal' and p.get('space_after_pt') is not None and p['space_after_pt']>1:
            finding('LNCS.paragraph_spacing.after',loc,'Extra paragraph space after body text','No extra blank paragraph separation',p['space_after_pt'],'Compare paragraph spacing with the official template','review')
        if p.get('has_image'):
            following=[q['text'] for q in paragraphs if p['index']<=q['index']<=p['index']+2]
            if not any(re.match(r'\s*(?:Fig\.?|Figure)\s*\d+',t,re.I) for t in following):finding('LNCS.captions.figure',loc,'No nearby numbered figure caption detected','Numbered figure caption below the figure',p['text'],'Review figure caption and placement','review')
    for table in doc.get('tables',[]):
        if not re.match(r'\s*Table\s*\d+',table.get('preceding_text',''),re.I):finding('LNCS.captions.table',f"table {table['number']}",'No preceding numbered table caption detected','Numbered table caption above the table',table.get('preceding_text',''),'Review table caption presence and placement','review')
    source=doc.get('source_text','')
    if source:
        clean=re.sub(r'(?<!\\)%[^\n]*','',source)
        for match in re.finditer(r'\\begin\{(figure\*?|table\*?)\}(.*?)\\end\{\1\}',clean,re.S):
            kind=match[1];body=match[2];loc='source line '+str(clean[:match.start()].count('\n')+1)
            if not re.search(r'\\caption(?:\[[^]]*\])?\s*\{',body):finding('LNCS.captions.'+kind,loc,'No literal caption detected in '+kind,'A numbered caption for each '+kind,kind,'Add the caption or request review of the caption macro','review','LaTeX source')
            elif kind.startswith('table') and '\\begin{tabular' in body and body.index('\\caption')>body.index('\\begin{tabular'):finding('LNCS.captions.table_position',loc,'Table caption is below its tabular content','Caption above table',kind,'Move the table caption above its content',method='LaTeX source')
        ids=set(doc.get('bibliography_ids',[]));cited=set()
        for m in re.finditer(r'\\cite\w*\*?(?:\[[^]]*\])*\{([^}]+)\}',clean):cited.update(k.strip() for k in m[1].split(','))
        for key in sorted(cited-ids):
            finding('LNCS.references.identifier','LaTeX bibliography','Citation key has no detected bibliography entry','Every citation resolves to an included bibliography entry',key,'Supply the .bib entry or correct the citation key','review','Source/BibTeX key comparison')
        if re.search(r'\\(?:renewcommand|def)\s*\{?\\(?:section|subsection|textwidth|textheight)',clean):finding('LNCS.headings.override','LaTeX source','Template command override detected','Preserve official class definitions','Template override','Review the override against conference instructions','review','LaTeX source')
    for category in ['headings','paragraph_spacing','figures','tables','captions','references']:
        checks.append({'check':'LNCS '+category,'status':'requires_review' if any(i['rule']['rule_id'].startswith('LNCS.'+category) and i['severity']=='review' for i in issues) else ('observed' if paragraphs or source else 'requires_review'),'source':SOURCE,'reason':'Supported observations checked; semantic correctness and unobserved layout remain subject to editorial review'})
    return issues,checks


def template_verified():
    """Match the retained publisher class to the recorded signed-distribution hash."""
    import json,zipfile
    from pathlib import Path
    from .settings import settings
    try:
        expected=json.loads(Path('profiles/lncs-provenance.json').read_text())['sha256']
        with zipfile.ZipFile(settings.storage/'conference-template.zip') as archive:
            candidates=[i for i in archive.infolist() if Path(i.filename).name=='llncs.cls']
            return len(candidates)==1 and candidates[0].file_size<1024*1024 and hashlib.sha256(archive.read(candidates[0])).hexdigest()==expected
    except (OSError,ValueError,KeyError,zipfile.BadZipFile):return False
