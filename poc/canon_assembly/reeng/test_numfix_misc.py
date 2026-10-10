"""Тесты мелких правок сборки/нумерации шага 11 (синтетика, без корпуса и Word): pytest reeng/test_numfix_misc.py"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import docx
from docx.oxml.ns import qn
from lxml import etree
import pynum, py_numfix, verify_canon, refidx

W = pynum.NS


def _numbering(lvls):
    xml = '<w:numbering xmlns:w="%s"><w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="multilevel"/>%s</w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num></w:numbering>' % (W, lvls)
    return etree.fromstring(xml)


def _para(ilvl, text):
    return etree.fromstring('<w:p xmlns:w="%s"><w:pPr><w:numPr><w:ilvl w:val="%d"/><w:numId w:val="1"/></w:numPr></w:pPr><w:r><w:t>%s</w:t></w:r></w:p>' % (W, ilvl, text))


def test_numfmt_none_parent_is_empty_and_literal_text_shown():
    # «%2%1.1» при numFmt none у уровня 0: Word даёт «1.1» (ДП-М1.030-04); lvlText «-» при none показывается как «-» (ДП-М1.020-06)
    nb = pynum.Numbering(_numbering(
        '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="none"/><w:lvlText w:val="8."/></w:lvl>'
        '<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%2%1.1"/></w:lvl>'
        '<w:lvl w:ilvl="2"><w:start w:val="1"/><w:numFmt w:val="none"/><w:lvlText w:val="-"/></w:lvl>'), None)
    assert nb.step(_para(1, 'a')) == '1.1'
    assert nb.step(_para(2, 'b')) == '-'


def test_unhide_web_keeps_toc_lines():
    d = docx.Document()
    body = d.element.body
    def add(xml):
        e = etree.fromstring(xml.replace('<w:p>', '<w:p xmlns:w="%s">' % W, 1)); body.insert(0, e); return e
    hid = add('<w:p><w:pPr><w:rPr><w:webHidden/></w:rPr></w:pPr><w:r><w:rPr><w:webHidden/></w:rPr><w:t>Приложение 1. Форма</w:t></w:r></w:p>')
    toc = add('<w:p><w:r><w:t>Приложение 2. Форма</w:t></w:r><w:r><w:rPr><w:webHidden/></w:rPr><w:tab/></w:r><w:r><w:rPr><w:webHidden/></w:rPr><w:t>78</w:t></w:r></w:p>')
    assert py_numfix.unhide_web(d) == 2
    assert hid.find('.//' + qn('w:webHidden')) is None and len(toc.findall('.//' + qn('w:webHidden'))) == 2


def test_toc_block_ends_on_prefix_repeat():
    # оглавление «на хранении», тело «на хранение»: точный повтор первой строки тела не совпал, но совпадёт по началу — тело не уходит в оглавление
    head = 'Приложение %d. Форма акта о приеме-передаче товарно-материальных ценностей на хранени%s (МХ-%d)'
    paras = [('', 'СОДЕРЖАНИЕ')] + [('', head % (i, 'и', i)) for i in (1, 2, 3)] + [('', head % (i, 'е', i)) for i in (1, 2, 3)]
    body = verify_canon.body_paras(paras)
    assert [t for _, t in body] == [head % (i, 'е', i) for i in (1, 2, 3)]


def test_locate_far_short_phrase_only_if_unique():
    class R(refidx.RefIndex):
        def __init__(self, S): self.S = S; self.off = [0]
    S = 'x' * 20000 + 'входныеданные' + 'y' * 100 + 'входныеданные'
    assert R(S).locate('входныеданные', 0) is None          # далеко и не единственная
    S2 = 'x' * 20000 + 'входныеданные'
    assert R(S2).locate('входныеданные', 0) is not None       # единственная — можно
