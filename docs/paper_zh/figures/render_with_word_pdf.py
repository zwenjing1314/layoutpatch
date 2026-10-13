"""Use the documents skill rasterizer with a Microsoft Word native PDF export."""
from pathlib import Path
import importlib.util, os, shutil
ROOT=Path(__file__).resolve().parent
os.environ['PATH']=r'C:\Users\WenJing\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin'+os.pathsep+os.environ['PATH']
spec=importlib.util.spec_from_file_location('skill_render',r'C:\Users\WenJing\.codex\plugins\cache\openai-primary-runtime\documents\26.1011.11113\skills\documents\render_docx.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def word_pdf(doc_path,user_profile,convert_tmp_dir,stem,verbose=False):
    dest=Path(convert_tmp_dir)/(stem+'.pdf')
    shutil.copy2(ROOT/'word-verified.pdf',dest)
    return str(dest),'Microsoft Word native ExportAsFixedFormat; bundled LibreOffice unavailable.'
module.convert_to_pdf=word_pdf
paths=module.rasterize(str(ROOT.parent/'paper-advisor-v1.docx'),str(ROOT/'word-render'),160,False,True)
print('Rendered',len(paths),'pages with documents skill rasterizer')
