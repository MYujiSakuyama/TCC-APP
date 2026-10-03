"""
parser.py - Módulo de Parsing de Operações e Notas de Corretagem em PDF (TCC)

Este módulo é responsável por ler e estruturar as operações de renda variável a
partir de Notas de Corretagem em PDF no padrão SINACOR da B3 (Clear, Rico, XP,
Inter, entre outras), única fonte de dados aceita pelo sistema.

Totalmente documentado e focado na precisão de extração dos dados reais.
"""

import re
import pandas as pd
from typing import List, Dict, Any, Tuple
import pypdf
import pdfplumber

from utils import Operacao, classificar_ativo_api


def extrair_texto_pdf(file_input: Any) -> str:
    """Extrai todo o conteúdo textual de um arquivo PDF de nota de corretagem."""
    texto_completo = ""
    try:
        if hasattr(file_input, 'seek'):
            file_input.seek(0)
        with pdfplumber.open(file_input) as pdf:
            for page in pdf.pages:
                txt = page.extract_text()
                if txt:
                    texto_completo += txt + "\n"
    except Exception:
        if hasattr(file_input, 'seek'):
            file_input.seek(0)
        reader = pypdf.PdfReader(file_input)
        for page in reader.pages:
            txt = page.extract_text()
            if txt:
                texto_completo += txt + "\n"

    return texto_completo


def _converter_valor_br(valor_str: str) -> float:
    """Converte valores monetários no formato brasileiro ('1.234,56') para float (1234.56)."""
    if not valor_str:
        return 0.0
    val_limpo = str(valor_str).replace(".", "").replace(",", ".")
    try:
        return float(val_limpo)
    except ValueError:
        return 0.0


# Linha de "Negócios realizados" no padrão SINCOR/B3. Exemplo real:
#
#   1-BOVESPA V FRACIONARIO BBSEGURIDADE ON NM 54 24,99 1.349,46 C
#   └─ bolsa  │ └ mercado   └ especificação     │  │     │        └ D/C
#             └ C/V                             │  │     └ valor da operação
#                                               │  └ preço unitário
#                                               └ quantidade
#
# O parse é ancorado nas colunas da direita (quantidade, preço, valor, D/C),
# porque o ticker não aparece na nota: a coluna traz a "Especificação do título".
PADRAO_NEGOCIO = re.compile(
    r'BOVESPA\s+([CV])\s+(\S+)\s+(.+?)\s+'      # C/V, tipo de mercado, especificação
    r'(\d+)\s+'                                  # quantidade
    r'(\d[\d.]*,\d{2})\s+'                       # preço unitário
    r'(\d[\d.]*,\d{2})\s+'                       # valor da operação
    r'[DC]\s*$',                                 # indicador Débito / Crédito
    re.IGNORECASE
)

# Códigos da coluna "Obs. (*)", que vem colada ao final da especificação.
# A letra 'C' é deixada de fora de propósito, para não consumir o sufixo "CI"
# das cotas de FIIs e ETFs.
PADRAO_OBS = re.compile(r'^[#ADHTXFYBLIP28]{1,2}$')


def _valor_do_rotulo(texto: str, rotulo: str, ultimo: bool = False) -> float:
    """
    Procura a linha do resumo da nota que contém o rótulo informado e devolve
    um valor monetário dessa linha.

    A busca considera apenas o trecho da linha após o rótulo, porque o resumo
    da nota é impresso em duas colunas lado a lado e elas caem na mesma linha
    de texto: 'Compras à vista 15.913,10 Taxa de liquidação 7,92 D'.

    ultimo=False pega o primeiro valor após o rótulo (taxas e emolumentos).
    ultimo=True pega o último valor, usado no IRRF, cuja linha é
    'I.R.R.F. s/ operações, base R$15.801,54 0,79' (o primeiro número é a base).
    """
    for linha in texto.splitlines():
        match = re.search(rotulo, linha, re.IGNORECASE)
        if not match:
            continue
        valores = re.findall(r'\d[\d.]*,\d{2}', linha[match.end():])
        if valores:
            return _converter_valor_br(valores[-1] if ultimo else valores[0])
    return 0.0


def _separar_obs(especificacao: str) -> Tuple[str, List[str]]:
    """
    Separa a especificação do título dos códigos da coluna 'Obs. (*)'.
    Em 'BLAU ON NM #2' devolve ('BLAU ON NM', ['#2']).
    """
    tokens = especificacao.split()
    obs = []
    while len(tokens) > 1 and PADRAO_OBS.match(tokens[-1]):
        obs.insert(0, tokens.pop().upper())
    return " ".join(tokens), obs


def _categoria_por_especificacao(especificacao: str) -> str:
    """
    Classifica o ativo pela própria especificação da nota, já que o ticker
    não é informado: 'FII ... CI' é fundo imobiliário, '... CI' é ETF e
    'ON / PN / UNT' são ações.
    """
    espec = especificacao.upper()
    if "FII" in espec or "FDO INV IMOB" in espec:
        return "FII"
    if espec.endswith(" CI") or espec.endswith("CI"):
        return "ETF"
    return "ACAO"


def parse_pdf_nota_corretagem(file_input: Any) -> pd.DataFrame:
    """
    Realiza o parse de um arquivo PDF de Nota de Corretagem da B3.
    Identifica:
    - Data do pregão
    - Operações de Compra (C) e Venda (V)
    - Especificação do título, quantidade e preço unitário
    - Categoria do ativo (ACAO / FII / ETF) e marcação de Day Trade
    - Taxas e IRRF do resumo, rateados proporcionalmente
    """
    texto = extrair_texto_pdf(file_input)

    # 1. Extração da Data do Pregão.
    # O cabeçalho é 'Nr. nota Folha Data pregão' e os valores vêm na linha
    # seguinte ('4535159 1 02/05/2022'), por isso a busca atravessa a quebra.
    data_nota = ""
    padrao_data = re.search(
        r'Data\s*preg[ãa]o[\s\S]{0,120}?(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE
    )
    if not padrao_data:
        padrao_data = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
    if padrao_data:
        data_nota = padrao_data.group(1)

    # 2. Extração das Operações (linhas de "Negócios realizados")
    operacoes_encontradas = []

    for linha in texto.splitlines():
        match = PADRAO_NEGOCIO.search(linha.strip())
        if not match:
            continue

        tipo_op, _mercado, especificacao_bruta, qtd_str, preco_str, _valor_str = match.groups()
        especificacao, obs = _separar_obs(especificacao_bruta)

        qtd = int(qtd_str)
        preco = _converter_valor_br(preco_str)
        if qtd <= 0 or preco <= 0.0 or not especificacao:
            continue

        operacoes_encontradas.append({
            "Data": data_nota,
            "Tipo": tipo_op.upper(),
            "Ticker": especificacao,
            "Quantidade": qtd,
            "Preco": preco,
            "Taxas": 0.0,
            # Na legenda da nota, a observação 'D' significa Day Trade
            "DayTrade": "D" in obs,
            "IRRF": 0.0,
            "Categoria": _categoria_por_especificacao(especificacao)
        })

    # 3. Extração de Taxas Totais e IRRF do Resumo da Nota
    taxas_totais = (
        _valor_do_rotulo(texto, r'Taxa\s*de\s*liquida[çc][ãa]o')
        + _valor_do_rotulo(texto, r'Emolumentos')
        + _valor_do_rotulo(texto, r'Corretagem|Taxa\s*Operacional')
        + _valor_do_rotulo(texto, r'Taxa\s*de\s*Registro')
    )
    irrf_total = _valor_do_rotulo(texto, r'I\.?R\.?R\.?F\.?', ultimo=True)

    # 4. Rateio proporcional ao valor de cada operação.
    # O IRRF ("dedo-duro") é retido apenas sobre as vendas, por isso é rateado
    # somente entre elas.
    if operacoes_encontradas:
        valores = {id(op): op["Quantidade"] * op["Preco"] for op in operacoes_encontradas}
        valor_total = sum(valores.values())
        valor_vendas = sum(v for op, v in zip(operacoes_encontradas, valores.values()) if op["Tipo"] == "V")

        for op in operacoes_encontradas:
            valor_op = valores[id(op)]
            if valor_total > 0:
                op["Taxas"] = round(taxas_totais * valor_op / valor_total, 2)
            if op["Tipo"] == "V" and valor_vendas > 0:
                op["IRRF"] = round(irrf_total * valor_op / valor_vendas, 2)

        # O arredondamento de cada parcela deixa centavos de sobra; o residual
        # é lançado na maior operação para que a soma feche com a nota.
        maior = max(operacoes_encontradas, key=lambda op: valores[id(op)])
        maior["Taxas"] = round(maior["Taxas"] + taxas_totais - sum(o["Taxas"] for o in operacoes_encontradas), 2)

        vendas = [o for o in operacoes_encontradas if o["Tipo"] == "V"]
        if vendas:
            maior_venda = max(vendas, key=lambda op: valores[id(op)])
            maior_venda["IRRF"] = round(maior_venda["IRRF"] + irrf_total - sum(o["IRRF"] for o in vendas), 2)

    df = pd.DataFrame(operacoes_encontradas)
    if df.empty:
        df = pd.DataFrame(columns=["Data", "Tipo", "Ticker", "Quantidade", "Preco", "Taxas", "DayTrade", "IRRF"])

    return df


def converter_dataframe_para_operacoes(
    df: pd.DataFrame,
    mapa_categorias: Dict[str, str] = None
) -> List[Operacao]:
    """
    Converte o DataFrame de operações em uma lista de objetos Operacao do utils.py.

    Os valores já chegam com os tipos corretos, pois são produzidos pelo parse da
    nota em PDF ou pelo lançamento manual da interface.
    """
    if mapa_categorias is None:
        mapa_categorias = {}

    lista_operacoes = []

    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip().upper()

        # A nota de corretagem em PDF já traz a categoria, deduzida da
        # especificação do título. Só consulta a API quando ela não vem,
        # caso do lançamento manual, em que o usuário digita o ticker.
        categoria_informada = str(row.get("Categoria", "") or "").strip().upper()
        if categoria_informada in ("ACAO", "FII", "ETF"):
            mapa_categorias[ticker] = categoria_informada
        elif ticker not in mapa_categorias:
            mapa_categorias[ticker] = classificar_ativo_api(ticker)

        categoria = mapa_categorias[ticker]
        tipo_op = str(row["Tipo"]).strip().upper()[:1]
        if tipo_op not in ("C", "V"):
            continue

        qtd = int(row["Quantidade"])
        preco = float(row["Preco"])
        taxas = float(row.get("Taxas", 0.0) or 0.0)
        day_trade = bool(row.get("DayTrade", False))
        irrf = float(row.get("IRRF", 0.0) or 0.0)

        # A data pode chegar como texto ou como Timestamp do pandas
        data_bruta = row["Data"]
        if isinstance(data_bruta, pd.Timestamp):
            data_str = data_bruta.strftime("%Y-%m-%d")
        else:
            data_str = str(data_bruta).strip()

        op = Operacao(
            data=data_str,
            tipo=tipo_op,
            ticker=ticker,
            quantidade=qtd,
            preco_unitario=preco,
            taxas=taxas,
            is_day_trade=day_trade,
            categoria=categoria,
            irrf=irrf
        )
        lista_operacoes.append(op)

    return lista_operacoes
