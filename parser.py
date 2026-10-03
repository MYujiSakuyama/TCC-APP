"""
parser.py - Módulo de Parsing de Operações e Notas de Corretagem em PDF (TCC)

Este módulo é responsável por ler e estruturar dados de operações a partir de:
1. Arquivos de Notas de Corretagem em formato PDF (Padrão SINCOR B3 - Rico, Clear, Inter, XP, etc.).
2. Planilhas em formato CSV e Excel (.xlsx / .xls).

Totalmente documentado e focado na precisão de extração dos dados reais.
"""

import re
import io
import pandas as pd
from typing import List, Dict, Any, Tuple
import pypdf
import pdfplumber

from utils import Operacao, classificar_ativo_api


def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    """Padroniza os nomes das colunas de um DataFrame lido."""
    mapeamento = {
        "data": "Data", "data operacao": "Data", "dt_operacao": "Data",
        "tipo": "Tipo", "tipo_op": "Tipo", "c/v": "Tipo", "operacao": "Tipo",
        "ticker": "Ticker", "ativo": "Ticker", "codigo": "Ticker",
        "quantidade": "Quantidade", "qtd": "Quantidade", "quant": "Quantidade",
        "preco": "Preco", "preço": "Preco", "preco_unitario": "Preco", "valor_unitario": "Preco",
        "taxas": "Taxas", "corretagem": "Taxas", "emolumentos": "Taxas", "custos": "Taxas",
        "daytrade": "DayTrade", "day_trade": "DayTrade", "is_day_trade": "DayTrade",
        "irrf": "IRRF", "imposto_retido": "IRRF", "irrf_retido": "IRRF"
    }

    novas_colunas = {}
    for col in df.columns:
        col_limpa = str(col).strip().lower()
        if col_limpa in mapeamento:
            novas_colunas[col] = mapeamento[col_limpa]
        else:
            novas_colunas[col] = str(col).strip().capitalize()

    df = df.rename(columns=novas_colunas)

    if "Taxas" not in df.columns:
        df["Taxas"] = 0.0
    if "DayTrade" not in df.columns:
        df["DayTrade"] = False
    if "IRRF" not in df.columns:
        df["IRRF"] = 0.0

    return df


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


def parse_pdf_nota_corretagem(file_input: Any) -> pd.DataFrame:
    """
    Realiza o parse de um arquivo PDF de Nota de Corretagem da B3.
    Identifica:
    - Data do pregão
    - Operações de Compra (C) e Venda (V)
    - Ticker dos ativos (ex: PETR4, VALE3, MXRF11)
    - Quantidade, Preço Unitário e Taxas Proporcionais
    - IRRF retido na fonte
    """
    texto = extrair_texto_pdf(file_input)
    linhas = texto.splitlines()

    # 1. Extração da Data do Pregão
    data_nota = ""
    padrao_data = re.search(r'(?:Data\s*pregão|Data\s*Pregão|Data):\s*(\d{2}/\d{2}/\d{4})', texto, re.IGNORECASE)
    if not padrao_data:
        padrao_data = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
    if padrao_data:
        data_nota = padrao_data.group(1)

    # 2. Extração das Operações (Linhas de Negócios Realizados)
    operacoes_encontradas = []

    # Regex para capturar tickers no padrão B3 (ex: PETR4, VALE3, MXRF11, BBDC4F)
    padrao_ticker = re.compile(r'\b([A-Z]{4}[0-9]{1,2}[Ff]?)\b')

    for linha in linhas:
        linha_str = linha.strip()
        if not linha_str:
            continue

        # Verifica se a linha contém indicação de BOVESPA / B3 e operação Compra (C) ou Venda (V)
        if "BOVESPA" in linha_str or "C" in linha_str.split() or "V" in linha_str.split():
            tokens = linha_str.split()
            
            # Procura por "C" ou "V" na linha
            tipo_op = None
            if "C" in tokens:
                tipo_op = "C"
            elif "V" in tokens:
                tipo_op = "V"

            if not tipo_op:
                continue

            # Procura o Ticker na linha
            match_ticker = padrao_ticker.search(linha_str)
            if match_ticker:
                ticker_bruto = match_ticker.group(1).upper()
                # Remove o 'F' final indicador de mercado fracionário se presente (ex: PETR4F -> PETR4)
                if len(ticker_bruto) > 5 and ticker_bruto.endswith("F") and not ticker_bruto.endswith("11F"):
                    ticker = ticker_bruto[:-1]
                else:
                    ticker = ticker_bruto

                # Procura por números na linha (Quantidade e Preço)
                # Formato típico de números com vírgula: 100 30,50 3.050,00
                numeros_br = re.findall(r'\b\d{1,3}(?:\.\d{3})*,\d{2}\b|\b\d+\b', linha_str)
                
                if len(numeros_br) >= 2:
                    try:
                        # O primeiro número inteiro costuma ser a quantidade
                        # Os seguintes são preço unitário e valor total
                        qtd = 0
                        preco = 0.0
                        
                        for num in numeros_br:
                            if "," not in num and int(num) > 0 and qtd == 0:
                                qtd = int(num)
                            elif "," in num and preco == 0.0:
                                preco = _converter_valor_br(num)

                        if qtd > 0 and preco > 0.0:
                            operacoes_encontradas.append({
                                "Data": data_nota,
                                "Tipo": tipo_op,
                                "Ticker": ticker,
                                "Quantidade": qtd,
                                "Preco": preco,
                                "Taxas": 0.0,
                                "DayTrade": False,
                                "IRRF": 0.0
                            })
                    except Exception:
                        pass

    # 3. Extração de Taxas Totais e IRRF do Resumo da Nota
    taxas_totais = 0.0
    irrf_total = 0.0

    match_taxa_liq = re.search(r'Taxa\s*de\s*liquidação\s*([\d\.,]+)', texto, re.IGNORECASE)
    match_emolumentos = re.search(r'Emolumentos\s*([\d\.,]+)', texto, re.IGNORECASE)
    match_corretagem = re.search(r'(?:Corretagem|Taxa\s*Operacional)\s*([\d\.,]+)', texto, re.IGNORECASE)
    match_irrf = re.search(r'(?:I\.R\.R\.F\.|IRRF)\s*(?:sobre\s*operações)?\s*([\d\.,]+)', texto, re.IGNORECASE)

    if match_taxa_liq:
        taxas_totais += _converter_valor_br(match_taxa_liq.group(1))
    if match_emolumentos:
        taxas_totais += _converter_valor_br(match_emolumentos.group(1))
    if match_corretagem:
        taxas_totais += _converter_valor_br(match_corretagem.group(1))
    if match_irrf:
        irrf_total = _converter_valor_br(match_irrf.group(1))

    # 4. Rateio das taxas e IRRF proporcionalmente entre as operações encontradas
    if operacoes_encontradas:
        qtd_ops = len(operacoes_encontradas)
        taxa_por_op = round(taxas_totais / qtd_ops, 2)
        irrf_por_op = round(irrf_total / qtd_ops, 2)

        for op in operacoes_encontradas:
            op["Taxas"] = taxa_por_op
            op["IRRF"] = irrf_por_op

    df = pd.DataFrame(operacoes_encontradas)
    if df.empty:
        df = pd.DataFrame(columns=["Data", "Tipo", "Ticker", "Quantidade", "Preco", "Taxas", "DayTrade", "IRRF"])
    
    return normalizar_colunas(df)


def ler_arquivo_operacoes(file_input: Any, nome_arquivo: str = "") -> pd.DataFrame:
    """
    Função principal de entrada. Detecta o formato do arquivo (PDF, CSV ou Excel)
    e chama o parser correspondente.
    """
    nome = nome_arquivo.lower() if nome_arquivo else str(file_input).lower()

    if nome.endswith(".pdf"):
        return parse_pdf_nota_corretagem(file_input)
    elif nome.endswith(".xlsx") or nome.endswith(".xls"):
        return normalizar_colunas(pd.read_excel(file_input))
    else:
        try:
            df = pd.read_csv(file_input, sep=";")
            if len(df.columns) <= 1:
                if hasattr(file_input, 'seek'):
                    file_input.seek(0)
                df = pd.read_csv(file_input, sep=",")
        except Exception:
            if hasattr(file_input, 'seek'):
                file_input.seek(0)
            df = pd.read_csv(file_input, sep=",")

        return normalizar_colunas(df)


def _para_float(valor: Any) -> float:
    """Converte um valor de célula para float, tratando vazios, NaN e formato brasileiro."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)

    texto = str(valor).strip()
    if not texto or texto.lower() in ("nan", "none", "-"):
        return 0.0
    # Valores com vírgula decimal ('1.234,56') exigem a conversão brasileira
    if "," in texto:
        return _converter_valor_br(texto)
    try:
        return float(texto)
    except ValueError:
        return 0.0


def _para_bool(valor: Any) -> bool:
    """
    Converte um valor de célula para booleano.
    Necessário porque bool('False') e bool('Não') resultariam em True.
    """
    if isinstance(valor, bool):
        return valor
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return False
    return str(valor).strip().lower() in ("1", "true", "t", "sim", "s", "yes", "y", "dt", "daytrade")


def converter_dataframe_para_operacoes(
    df: pd.DataFrame,
    mapa_categorias: Dict[str, str] = None
) -> List[Operacao]:
    """
    Converte o DataFrame extraído em uma lista de objetos Operacao do utils.py.
    """
    if mapa_categorias is None:
        mapa_categorias = {}

    lista_operacoes = []

    for _, row in df.iterrows():
        ticker = str(row["Ticker"]).strip().upper()

        if ticker not in mapa_categorias:
            mapa_categorias[ticker] = classificar_ativo_api(ticker)

        categoria = mapa_categorias[ticker]
        tipo_bruto = str(row["Tipo"]).strip().upper()
        if not tipo_bruto:
            continue
        tipo_op = tipo_bruto[0]

        qtd = int(_para_float(row["Quantidade"]))
        preco = _para_float(row["Preco"])
        taxas = _para_float(row.get("Taxas", 0.0))
        day_trade = _para_bool(row.get("DayTrade", False))
        irrf = _para_float(row.get("IRRF", 0.0))

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
