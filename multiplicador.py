"""
multiplicador.py - Módulo de Simulação e Ajuste de Escala de Operações (TCC IFPR)

Este módulo foi desenvolvido para apoiar a demonstração acadêmica do Trabalho de
Conclusão de Curso (TCC) no Instituto Federal do Paraná (IFPR - Campus Londrina).

Contexto da Regra Fiscal:
Conforme a legislação da Receita Federal do Brasil (RFB), vendas de ações no mercado
à vista (Swing Trade) cujo total seja igual ou inferior a R$ 20.000,00 no mês calendário
são ISENTAS de Imposto de Renda sobre o ganho de capital.

Problema:
A nota de corretagem real de teste padrão utilizada no projeto (b3_one_page.pdf) totaliza
R$ 15.801,54 em vendas de ações. Como este montante é inferior a R$ 20.000,00, o sistema
aplica a isenção fiscal, resultando em imposto R$ 0,00 e DARF R$ 0,00. Embora correto
segundo a legislação, esse cenário não evidencia o fluxo completo de cálculo de alíquotas,
compensação de IRRF e geração do DARF durante a apresentação do trabalho.

Solução:
Este módulo disponibiliza funções para aplicar um fator multiplicador (2x por padrão)
sobre as operações extraídas do PDF, dobrando quantidades, taxas proporcionais e IRRF retido,
elevando o volume de vendas de R$ 15.801,54 para R$ 31.603,08. Dessa forma, ultrapassa o limite
de isenção e viabiliza a demonstração prática da apuração tributária completa.
"""

from typing import List, Optional
import pandas as pd
from calculadora_ir import Operacao


def aplicar_multiplicador_df(
    df: pd.DataFrame,
    fator: float = 2.0,
    apenas_pdf: bool = True
) -> pd.DataFrame:
    """
    Aplica o fator multiplicador nas colunas 'Quantidade', 'Taxas' e 'IRRF' do DataFrame.

    Parâmetros:
        df: pd.DataFrame contendo as operações (Data, Tipo, Ticker, Quantidade, Preco, Taxas, etc.)
        fator: Fator pelo qual as operações serão multiplicadas (padrão: 2.0).
        apenas_pdf: Se True e existir a coluna 'Origem', multiplica apenas as linhas onde
                    Origem == 'PDF'. Caso contrário, multiplica todas as linhas.

    Retorna:
        pd.DataFrame: Cópia do DataFrame com os valores ajustados.
    """
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()

    df_mod = df.copy()

    if fator == 1.0:
        return df_mod

    # Identifica linhas a serem multiplicadas
    if apenas_pdf and "Origem" in df_mod.columns:
        mascara = df_mod["Origem"] == "PDF"
    else:
        mascara = pd.Series(True, index=df_mod.index)

    if "Quantidade" in df_mod.columns:
        df_mod.loc[mascara, "Quantidade"] = (
            df_mod.loc[mascara, "Quantidade"].astype(float) * fator
        ).round().astype(int)

    if "Taxas" in df_mod.columns:
        df_mod.loc[mascara, "Taxas"] = (
            df_mod.loc[mascara, "Taxas"].astype(float) * fator
        ).round(2)

    if "IRRF" in df_mod.columns:
        df_mod.loc[mascara, "IRRF"] = (
            df_mod.loc[mascara, "IRRF"].astype(float) * fator
        ).round(2)

    return df_mod


def aplicar_multiplicador_operacoes(
    operacoes: List[Operacao],
    fator: float = 2.0
) -> List[Operacao]:
    """
    Aplica o fator multiplicador diretamente sobre uma lista de objetos Operacao.

    Parâmetros:
        operacoes: Lista de instâncias de Operacao.
        fator: Fator multiplicador (padrão: 2.0).

    Retorna:
        List[Operacao]: Nova lista com as operações ajustadas.
    """
    if not operacoes or fator == 1.0:
        return list(operacoes) if operacoes else []

    novas_ops: List[Operacao] = []
    for op in operacoes:
        nova_qtd = int(round(op.quantidade * fator))
        novas_taxas = round(op.taxas * fator, 2)
        novo_irrf = round(op.irrf * fator, 2)

        novas_ops.append(Operacao(
            data=op.data,
            tipo=op.tipo,
            ticker=op.ticker,
            quantidade=nova_qtd,
            preco_unitario=op.preco_unitario,
            taxas=novas_taxas,
            is_day_trade=op.is_day_trade,
            categoria=op.categoria,
            irrf=novo_irrf
        ))

    return novas_ops
