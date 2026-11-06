import io,zipfile,json
import pytest
from docx import Document
from app.documents import safe_zip,inspect_document
from app.review import review

def test_zip_traversal(tmp_path):
    p=tmp_path/'bad.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('../escaped','x')
    with pytest.raises(ValueError,match='Unsafe'):safe_zip(p,tmp_path/'out')
def test_docx_and_real_findings(tmp_path):
    d=Document();d.add_paragraph('Abstract');d.add_paragraph('The the results are reproducible.');d.add_paragraph('Keywords: testing');d.add_paragraph('References')
    p=tmp_path/'sample.docx';d.save(p)
    doc=inspect_document(p)
    issues,checks=review(doc,'ieee','paper')
    assert any(i['category']=='writing' for i in issues)
    assert any(i['category']=='publisher' for i in issues)
    assert doc['sections'] and doc['text']
