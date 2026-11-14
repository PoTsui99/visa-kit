import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1] / 'skills' / 'uk-visitor-visa'
def load(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
preflight=load('preflight_pdfs')
printer=load('build_print_pack')

class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.a=self.pdf('First.pdf',1);self.b=self.pdf('Second.pdf',2)
    def tearDown(self):
        self.tmp.cleanup()
    def pdf(self,name,pages,password=None):
        p=self.base/name;p.parent.mkdir(parents=True,exist_ok=True)
        w=PdfWriter()
        for _ in range(pages):w.add_blank_page(width=300,height=400)
        if password:w.encrypt(password)
        with p.open('wb') as f:w.write(f)
        return p
    def test_valid_and_nonmutating(self):
        before=[p.read_bytes() for p in [self.a,self.b]]
        r=preflight.inspect_files([self.a,self.b])
        self.assertEqual(r['status'],'passed')
        self.assertEqual([d['pages'] for d in r['documents']],[1,2])
        self.assertEqual([p.read_bytes() for p in [self.a,self.b]],before)
    def test_encrypted_rejected(self):
        p=self.pdf('Encrypted.pdf',1,'fixture-only')
        r=preflight.inspect_files([p])
        self.assertEqual(r['status'],'blocked')
        self.assertTrue(r['documents'][0]['encrypted'])
    def test_limit_exclusive(self):
        n=self.a.stat().st_size
        self.assertEqual(preflight.inspect_files([self.a],n)['status'],'blocked')
        self.assertEqual(preflight.inspect_files([self.a],n+1)['status'],'passed')
    def test_duplicate_names_rejected(self):
        p=self.pdf('nested/First.pdf',1)
        r=preflight.inspect_files([self.a,p])
        self.assertTrue(all('duplicate_filename' in x['errors'] for x in r['documents']))
    def test_bad_name_missing_and_corrupt(self):
        cn=self.pdf('测试.pdf',1);bad=self.base/'Bad.pdf';bad.write_text('not a PDF')
        r=preflight.inspect_files([cn,bad,self.base/'Missing.pdf'])
        self.assertEqual(r['status'],'blocked')
        self.assertTrue(all(x['errors'] for x in r['documents']))
    def test_cli_blocks_overwriting_input(self):
        before=self.a.read_bytes()
        p=subprocess.run([sys.executable,str(ROOT/'scripts/preflight_pdfs.py'),'--files',str(self.a),'--json-output',str(self.a)],capture_output=True)
        self.assertNotEqual(p.returncode,0);self.assertEqual(self.a.read_bytes(),before)
    def test_print_pack_integrity_and_idempotence(self):
        dest=self.base/'To_Print';r=printer.build_print_pack(self.a,self.b,dest)
        self.assertEqual([x['pages'] for x in r['documents']],[1,2])
        self.assertEqual((dest/'01_Appointment_Confirmation.pdf').read_bytes(),self.a.read_bytes())
        self.assertEqual((dest/'02_UKVI_Document_Checklist.pdf').read_bytes(),self.b.read_bytes())
        self.assertEqual(printer.build_print_pack(self.a,self.b,dest)['status'],'copied_and_verified')
    def test_print_conflict_is_checked_before_copy(self):
        dest=self.base/'To_Print';dest.mkdir()
        conflict=dest/'02_UKVI_Document_Checklist.pdf';conflict.write_bytes(b'do not replace')
        with self.assertRaises(FileExistsError):printer.build_print_pack(self.a,self.b,dest)
        self.assertEqual(conflict.read_bytes(),b'do not replace')
        self.assertFalse((dest/'01_Appointment_Confirmation.pdf').exists())
    def test_print_rejects_extra_pdf(self):
        dest=self.base/'To_Print';dest.mkdir();(dest/'Old.pdf').write_bytes(self.a.read_bytes())
        with self.assertRaises(FileExistsError):printer.build_print_pack(self.a,self.b,dest)
    def test_print_rejects_encryption_and_same_source(self):
        enc=self.pdf('Locked.pdf',1,'fixture-only')
        with self.assertRaises(ValueError):printer.build_print_pack(enc,self.b,self.base/'p1')
        with self.assertRaises(ValueError):printer.build_print_pack(self.a,self.a,self.base/'p2')
        self.assertFalse((self.base/'p1').exists())
    def test_cli_normal_run(self):
        report=self.base/'report.json'
        p=subprocess.run([sys.executable,str(ROOT/'scripts/preflight_pdfs.py'),'--files',str(self.a),str(self.b),'--json-output',str(report)],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertTrue(report.is_file())
        p=subprocess.run([sys.executable,str(ROOT/'scripts/build_print_pack.py'),'--appointment',str(self.a),'--checklist',str(self.b),'--destination',str(self.base/'CLI_Print')],capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)

if __name__=='__main__':unittest.main(verbosity=2)
