import sys, pathlib
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
from backend.tools import xml_parser


def test_parse_minimal_xml():
    xml = """<?xml version="1.0"?>
    <NFe>
      <infNFe>
        <ide><nNF>123</nNF></ide>
        <emit><xNome>Empresa X</xNome><CNPJ>12345678000195</CNPJ><IE>12345</IE></emit>
        <dest><xNome>Cliente Y</xNome><CPF>12345678901</CPF></dest>
        <det><prod><xProd>Item A</xProd><qCom>2</qCom><vUnCom>10.00</vUnCom><vProd>20.00</vProd><CFOP>5102</CFOP></prod></det>
        <total><ICMSTot><vProd>20.00</vProd><vNF>20.00</vNF></ICMSTot></total>
      </infNFe>
    </NFe>"""
    parsed = xml_parser.parse_xml_string(xml)
    assert parsed['emitente']['razao_social'] == 'Empresa X'
    assert parsed['destinatario']['cnpj_cpf'] == '12345678901'
    assert parsed['total'] == 20.0
