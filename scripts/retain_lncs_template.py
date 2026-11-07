"""Retain publisher class redistributed by the signed Debian TeX Live package, with provenance."""
import hashlib,json,subprocess,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
cls=subprocess.check_output(['docker','run','--rm','--network=none','--entrypoint','sh','paperflow-tex:local','-c','cat "$(kpsewhich llncs.cls)"'])
assert b'Springer Verlag' in cls and b'12.2cm' in cls and b'19.3cm' in cls
package=subprocess.check_output(['docker','run','--rm','--network=none','--entrypoint','sh','paperflow-tex:local','-c',"dpkg-query -W -f='${Package} ${Version}' texlive-publishers"],text=True)
provenance={'publisher':'Springer Verlag','class':'LLNCS 2.22 (2022-09-05)','redistribution':'Debian signed package '+package,'publisher_reference':'https://resource-cms.springernature.com/springer-cms/rest/v1/content/19238648/data/v8','sha256':hashlib.sha256(cls).hexdigest(),'declared_text_width_mm':122,'declared_text_height_mm':193,'body_font_pt':10,'body_font_basis':'LLNCS loads article with no fontsize option; article default is 10pt','unverified':['conference page limit','publisher DOCX style mapping','semantic/figure/caption requirements']}
(root/'data').mkdir(exist_ok=True)
with zipfile.ZipFile(root/'data/conference-template.zip','w') as z:z.writestr('llncs.cls',cls);z.writestr('provenance.json',json.dumps(provenance,indent=2))
(root/'profiles/lncs-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
profile={'name':'Springer LNCS class 2.22','version':'llncs-2.22','source':provenance['publisher_reference'],'requirements':{'text_width_mm':122,'text_height_mm':193,'font_size_pt':10,'columns':1,'tolerance_mm':1},'note':'Verified against the publisher class redistributed in signed TeX Live. No conference-specific page limit or unverified publisher requirements are asserted. DOCX body textblock dimensions are compared against class dimensions; style equivalence requires final editorial acknowledgment.'}
(root/'profiles/conference-demo.json').write_text(json.dumps(profile,indent=2)+'\n');print('Official LNCS class retained; SHA256',provenance['sha256'])
