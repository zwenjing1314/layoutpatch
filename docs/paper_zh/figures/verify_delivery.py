from pathlib import Path
import re,json,zipfile,hashlib
from lxml import etree
from pypdf import PdfReader
from PIL import Image
ROOT=Path(__file__).resolve().parent.parent
ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
with zipfile.ZipFile(ROOT/'paper-advisor-v1.docx') as z:
    xml=etree.fromstring(z.read('word/document.xml'))
    texts=''.join(xml.xpath('//w:t/text()',namespaces=ns))
    maths=xml.xpath('//m:oMath',namespaces=ns)
    media=[n for n in z.namelist() if n.startswith('word/media/')]
    result={'docx_bytes':(ROOT/'paper-advisor-v1.docx').stat().st_size,'tables':len(xml.xpath('//w:tbl',namespaces=ns)),'editable_math_objects':len(maths),'embedded_images':len(media),'display_equation_numbers':re.findall(r'\((\d+)\)',texts),'page_count':len(PdfReader(ROOT/'figures/word-verified.pdf').pages)}
    result['unexpected_body_material']=[t for t in ['mermaid','写作核对备注','C:/Users/','待办列表','\\frac','\\tag','\\begin','![' ] if t in texts]
    expected=['2407.01449','2512.02660','2510.27261','2501.08828','2511.15090','2204.08387']
    result['arxiv_identifiers_intact']=all('arXiv:'+x in texts for x in expected)
    result['formula_numbers_complete']=result['display_equation_numbers']==[str(i) for i in range(1,22)]
    md=(ROOT/'manuscript-illustrated.md').read_text(encoding='utf-8')
    body,refs=md.split('# 参考文献',1)
    result['citation_keys']=sorted(set(re.findall(r'\[([A-Za-z][A-Za-z0-9]*\d{4})\]',body)))
    result['reference_keys']=sorted(re.findall(r'^\[([A-Za-z][A-Za-z0-9]*\d{4})\]',refs,re.M))
    result['citations_match']=result['citation_keys']==result['reference_keys']
    result['figures']={n:Image.open(ROOT/'figures'/n).size for n in ['figure-1-task.png','figure-2-methods.png']}
    result['docx_sha256']=hashlib.sha256((ROOT/'paper-advisor-v1.docx').read_bytes()).hexdigest()
(ROOT/'figures/delivery-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
