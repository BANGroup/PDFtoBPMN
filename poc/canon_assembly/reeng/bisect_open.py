"""Бисекция «Файл поврежден»: открывает в Word (op dump, один Word за раз) копии canon.docx с урезанным телом/подменёнными частями.
python3 bisect_open.py <canon.docx> body N        # тело: первые N элементов + финальный sectPr
python3 bisect_open.py <canon.docx> swap part ref.docx   # часть (напр. word/numbering.xml) из ref.docx"""
import sys, os, zipfile, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wordrun
from lxml import etree
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def variant(src, mode, a, b=None):
    z = zipfile.ZipFile(src); out = '/tmp/bisect_variant.docx'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zo:
        for it in z.infolist():
            data = z.read(it.filename)
            if mode == 'body' and it.filename == 'word/document.xml':
                root = etree.fromstring(data); body = root.find(W + 'body'); kids = list(body)
                lo, hi = (int(a), int(b)) if b else (0, int(a))
                for i, k in enumerate(kids):
                    if k.tag != W + 'sectPr' and not (lo <= i < hi): body.remove(k)
                if not len(body.findall(W + 'p')): etree.SubElement(body, W + 'p')
                data = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            if mode == 'swap' and it.filename == a: data = zipfile.ZipFile(b).read(a)
            zo.writestr(it, data)
    return out


def opens(path):
    tag = 'bis_ok'; shutil.copy(path, wordrun.wsl(tag + '.docx'))
    t = wordrun.wsl(tag + '.txt')
    if os.path.exists(t): os.remove(t)
    r = wordrun.run([{'op': 'dump', 'src': wordrun.winpath(tag + '.docx'), 'out': wordrun.winpath(tag + '.txt')}], tag, 600)
    return os.path.exists(t), r['log'][-150:]


if __name__ == '__main__':
    src, mode = sys.argv[1], sys.argv[2]
    v = variant(src, mode, *sys.argv[3:])
    print(opens(v))
