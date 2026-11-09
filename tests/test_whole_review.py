"""Provider-contract unit tests use explicit stubs; these are not real Gemini acceptance evidence."""
from pathlib import Path
import pytest
from app import whole_review as wr
from app.settings import settings

def test_exact_whole_document_partition_and_late_issue(tmp_path,monkeypatch):
    text='Abstract\n'+('A reproducible manuscript paragraph.\n'*2000)+'\nConclusion\nThe the final sentence.'
    parts=list(wr.chunks(text,4096));assert ''.join(p.text for p in parts)==text
    monkeypatch.setattr(settings,'ai_provider','gemini');monkeypatch.setattr(settings,'ai_api_key','unit-test-placeholder');monkeypatch.setattr(settings,'ai_model','test-model');monkeypatch.setattr(settings,'review_chunk_chars',4096)
    seen=[]
    def provider(chunk):
        seen.append(chunk.text)
        return ([{'problem':'Repeated adjacent word','suggestion':'Review repetition','evidence':'The the','confidence':1}] if 'The the' in chunk.text else []),{'response_id':'explicit-unit-stub','model':'test-model'}
    monkeypatch.setattr(wr,'_call_ai',provider)
    findings,coverage=wr.run(text,'AI proofreading',tmp_path)
    assert coverage['coverage_ratio']==1 and coverage['status']=='completed'
    assert coverage['reviewed_characters']==len(text)
    assert findings[0]['offset']>40000
    unique=len({(part.section,part.review_text) for part in parts})
    assert len(seen)==unique
    # Recovery reuses successful persisted chunks and makes no additional calls.
    wr.run(text,'AI proofreading',tmp_path);assert len(seen)==unique

def test_failed_chunk_is_not_reported_covered_and_recovers(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'ai_provider','gemini');monkeypatch.setattr(settings,'ai_api_key','unit-test-placeholder');monkeypatch.setattr(settings,'ai_model','test-model');monkeypatch.setattr(settings,'review_chunk_chars',1000);monkeypatch.setattr(settings,'review_retries',1)
    text=('Long section. '*300)+' Tail.'
    def provider(chunk):
        if chunk.number==1:raise TimeoutError('DO NOT LOG MANUSCRIPT OR CREDENTIALS')
        return [],{'response_id':'explicit-unit-stub'}
    monkeypatch.setattr(wr,'_call_ai',provider)
    _,coverage=wr.run(text,'AI proofreading',tmp_path)
    assert coverage['status']=='failed' and coverage['coverage_ratio']<1 and coverage['failed_chunks']==1
    assert 'DO NOT LOG' not in str(coverage)
    calls=[]
    monkeypatch.setattr(wr,'_call_ai',lambda c:(calls.append(c.number) or [],{'response_id':'explicit-unit-stub'}))
    _,coverage=wr.run(text,'AI proofreading',tmp_path)
    assert coverage['coverage_ratio']==1 and calls==[1]

def test_unsubstantiated_ai_evidence_fails_the_chunk(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'ai_provider','gemini');monkeypatch.setattr(settings,'ai_api_key','unit-test-placeholder');monkeypatch.setattr(settings,'ai_model','test-model');monkeypatch.setattr(settings,'review_retries',1)
    monkeypatch.setattr(wr,'_call_ai',lambda c:([{'problem':'Made up','suggestion':'Invalid','evidence':'NOT IN SOURCE','confidence':1}],{}))
    findings,coverage=wr.run('An actual manuscript.','AI proofreading',tmp_path)
    assert findings==[] and coverage['status']=='failed' and coverage['reviewed_characters']==0

def test_test_mail_cannot_escape_to_external_smtp(monkeypatch):
    from app.mail import send_smtp
    from email.message import EmailMessage
    monkeypatch.setattr(settings,'mail_mode','DEMO');monkeypatch.setattr(settings,'smtp_host','smtp.external.example');monkeypatch.setattr(settings,'smtp_port',587)
    with pytest.raises(ValueError,match='restricted'):send_smtp(EmailMessage())
