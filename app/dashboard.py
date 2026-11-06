import os,io,csv
import requests
import streamlit as st
st.set_page_config(page_title='PaperFlow AI',page_icon='📚',layout='wide')
st.markdown('<style>.stApp{background:#f5f7fc}h1,h2,h3{color:#173456}div[data-testid="stMetric"]{background:white;padding:18px;border-radius:12px}</style>',unsafe_allow_html=True)
st.title('📚 Conference Proceedings Control Center')
st.caption('PaperFlow AI · Evidence-based review · Editorial control')
base=os.getenv('API_URL','http://127.0.0.1:8000')
token=st.sidebar.text_input('Administrator token',type='password',value=os.getenv('ADMIN_TOKEN',''))
headers={'Authorization':'Bearer '+token}
def call(method,path,**kwargs):
    r=requests.request(method,base+path,headers=headers,timeout=120,**kwargs)
    if not r.ok: st.error(r.text);st.stop()
    return r
if not token: st.info('Enter the administrator token to continue.');st.stop()
rows=call('GET','/papers').json()
a,b,c=st.columns(3)
a.metric('Submissions',len(rows));b.metric('Processing',sum(r['status'] in ['Submitted','Processing','Resubmitted'] for r in rows));c.metric('Approved',sum(r['status']=='Approved' for r in rows))
tabs=st.tabs(['Intake','Papers & review','Publication'])
with tabs[0]:
    profile=st.selectbox('Publisher profile',['ieee','lncs','ccis'])
    st.caption('Profiles require official conference rules before a compliance decision. Unverified properties require editorial review.')
    files=st.file_uploader('Drop manuscript files',type=['docx','pdf','tex','zip'],accept_multiple_files=True)
    metadata=st.file_uploader('Optional metadata CSV (filename,title,authors,email,track,affiliation)',type=['csv'])
    if st.button('Register batch',disabled=not files):
        lookup={r['filename']:r for r in csv.DictReader(io.StringIO(metadata.getvalue().decode('utf-8-sig')))} if metadata else {}
        for f in files:
            m={k:v for k,v in lookup.get(f.name,{}).items() if k in {'title','authors','email','track','affiliation'}};m['profile']=profile
            r=requests.post(base+'/submissions',headers=headers,files={'file':(f.name,f.getvalue())},data=m,timeout=120)
            st.write(f.name,r.status_code,r.json())
with tabs[1]:
    query=st.text_input('Search title, author, paper ID')
    filtered=[r for r in rows if query.lower() in str(r).lower()]
    st.dataframe(filtered,width='stretch')
    if st.button('Refresh queue'): st.rerun()
    if filtered:
        pid=st.selectbox('Open paper',[r['id'] for r in filtered])
        d=call('GET','/papers/'+pid).json();st.json(d['paper'])
        for v in d['versions']:
            with st.expander(f"Version {v['number']} · {v['state']}",expanded=v['number']==d['paper']['latest']):
                if v['error']:st.error(v['error'])
                severity=st.multiselect('Severity',['error','warning','review'],default=['error','warning','review'],key=v['id'])
                st.dataframe([i for i in v['result'].get('issues',[]) if i['severity'] in severity],width='stretch')
                st.json(v['result'].get('comparison',{}))
                st.download_button('Original manuscript',call('GET',f"/versions/{v['id']}/download").content,file_name=v['filename'],key='dl'+v['id'])
                if st.button('Retry validation',key='retry'+v['id']):call('POST',f"/versions/{v['id']}/retry");st.rerun()
        st.subheader('Editorial actions')
        with st.form('metadata'):
            title=st.text_input('Title',d['paper']['title']);authors=st.text_input('Authors (semicolon separated)',d['paper']['authors'])
            affiliation=st.text_input('Affiliations',d['paper']['affiliation']);email=st.text_input('Corresponding email',d['paper']['email']);track=st.text_input('Track',d['paper']['track'])
            if st.form_submit_button('Save metadata (invalidates approval)'):
                call('PATCH','/papers/'+pid,json=dict(title=title,authors=authors,affiliation=affiliation,email=email,track=track));st.rerun()
        latest=d['versions'][-1]
        if latest['state']=='Complete':
            st.download_button('Correction PDF',call('GET','/versions/'+latest['id']+'/report').content,file_name='correction-report.pdf')
            st.download_button('Correction HTML',call('GET','/versions/'+latest['id']+'/report?format=html').content,file_name='correction-report.html')
            if latest['result'].get('document',{}).get('rendered_pdf'):
                preview=call('GET','/versions/'+latest['id']+'/preview').content
                st.download_button('Rendered manuscript PDF',preview,file_name='manuscript.pdf')
                with st.expander('Document preview'):
                    import base64
                    encoded=base64.b64encode(preview).decode()
                    st.markdown('<iframe title="Manuscript preview" src="data:application/pdf;base64,'+encoded+'" width="100%" height="650"></iframe>',unsafe_allow_html=True)
            st.json(latest['result'].get('checks',[]))
            acknowledged=st.checkbox('I reviewed unresolved findings, metadata, abstract extraction, and skipped checks')
            if st.button('Approve current version',disabled=not acknowledged):call('POST','/papers/'+pid+'/approve',json={'acknowledge_review':True});st.rerun()
            if st.button('Prepare correction email'):st.json(call('POST','/papers/'+pid+'/messages').json())
            if st.button('Normalize DOCX nonbreaking spaces and revalidate'):st.json(call('POST','/papers/'+pid+'/correction').json())
        if st.button('Create secure revision link'):st.code(call('POST','/papers/'+pid+'/revision-link').json()['url'])
        st.subheader('Author communications')
        for m in call('GET','/messages').json():
            if m['paper_id']!=pid:continue
            st.write(m['subject'],m['state']);st.text(m['body'])
            if m['state']=='Pending approval' and st.button('Approve email',key='approve'+m['id']):call('POST','/messages/'+m['id']+'/approve');st.rerun()
            if m['state']=='Approved' and st.button('Send approved email',key='send'+m['id']):call('POST','/messages/'+m['id']+'/send');st.rerun()
        st.dataframe(d['audit'],width='stretch')
with tabs[2]:
    conference=st.text_input('Conference name');information=st.text_area('Conference information')
    approved=[r for r in rows if r['status']=='Approved']
    selected=st.multiselect('Editor-approved papers',[r['id'] for r in approved],format_func=lambda pid:next(r['title'] for r in approved if r['id']==pid))
    confirmed=st.checkbox('I authorize publication of the selected approved versions')
    if st.button('Assemble publication',disabled=not(selected and confirmed and conference)):
        st.session_state['publication']=call('POST','/publications',json={'conference':conference,'information':information,'paper_ids':selected,'confirm_editorial_approval':confirmed}).json()
    if 'publication' in st.session_state:
        pub=st.session_state['publication']
        for filename in pub['files']:
            st.download_button(filename,call('GET','/publications/'+pub['publication_id']+'/'+filename).content,file_name=filename,key='pub'+filename)
    st.subheader('Official conference profiles')
    profiles=call('GET','/profiles').json();name=st.selectbox('Profile to configure',list(profiles))
    config=st.text_area('Profile JSON (new version required)',value=__import__('json').dumps(profiles[name],indent=2),height=250)
    if st.button('Save official rule profile'):
        try:parsed=__import__('json').loads(config)
        except ValueError:st.error('Invalid JSON');st.stop()
        st.json(call('PUT','/profiles/'+name,json=parsed).json())
    if st.button('Check overdue revisions'):st.json(call('GET','/reminders/due').json())
