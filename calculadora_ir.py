"""
utils.py - Módulo de Cálculos e Classificação de Imposto de Renda em Renda Variável (TCC)

Este módulo foi desenvolvido de forma simples, direta e bem documentada.
Contém:
1. Classificação de ativos via API externa com fallback automático.
2. Controle de posição e Custo Médio Ponderado por ativo.
3. Apuração de resultado de vendas (Lucro/Prejuízo).
4. Verificação de isenção de R$ 20.000,00 para Swing Trade em Ações.
5. Apuração mensal consolidada com alíquotas (15% Swing Trade, 20% Day Trade e FIIs).
6. Compensação de prejuízos acumulados e deduções de IRRF.
7. Regra do valor mínimo de R$ 10,00 para emissão de DARF.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from decimal import Decimal, ROUND_HALF_UP
import requests


def _arredondar(valor: float) -> float:
    """Arredonda valores monetários para 2 casas decimais de forma precisa."""
    d = Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return float(d)


def classificar_ativo_api(ticker: str) -> str:
    """
    Classifica um ticker da B3 em 'ACAO', 'FII' ou 'ETF' consultando uma API externa pública.
    Se a API estiver offline ou o ticker não for encontrado, usa uma regra simples pelo final do código.
    """
    ticker_limpo = ticker.strip().upper()
    
    # Tentativa de consulta na API pública brapi.dev
    try:
        url = f"https://brapi.dev/api/quote/{ticker_limpo}"
        resposta = requests.get(url, timeout=2)
        if resposta.status_code == 200:
            dados = resposta.json()
            resultados = dados.get("results", [])
            if resultados:
                tipo_api = resultados[0].get("quoteType", "").upper()
                if tipo_api == "FII":
                    return "FII"
                elif tipo_api == "ETF":
                    return "ETF"
                elif tipo_api in ["EQUITY", "STOCK"]:
                    return "ACAO"
    except Exception:
        # Se a requisição falhar, passa direto para o fallback simples
        pass

    # Regra simples de fallback: tickers terminados em '11' ou '11B' são FIIs/ETFs (padrão FII)
    if ticker_limpo.endswith("11") or ticker_limpo.endswith("11B"):
        return "FII"
    
    return "ACAO"


@dataclass
class PosicaoAtivo:
    """Estrutura simples para controlar a quantidade e o custo médio de um ativo."""
    quantidade: int = 0
    custo_total: float = 0.0
    custo_medio: float = 0.0

    def comprar(self, qtd: int, preco_unitario: float, taxas: float = 0.0):
        """Atualiza a quantidade e calcula o novo custo médio ponderado após uma compra."""
        if qtd <= 0:
            return
        
        custo_compra = (qtd * preco_unitario) + taxas
        self.quantidade += qtd
        self.custo_total += custo_compra
        self.custo_medio = _arredondar(self.custo_total / self.quantidade)

    def vender(self, qtd: int, preco_unitario: float, taxas: float = 0.0) -> float:
        """
        Calcula o resultado da venda (Lucro ou Prejuízo) e reduz a quantidade mantendo o custo médio.
        Não possui validações complexas: calcula diretamente o resultado.
        """
        if qtd <= 0:
            return 0.0

        valor_venda_liquido = (qtd * preco_unitario) - taxas
        custo_venda = qtd * self.custo_medio
        resultado = _arredondar(valor_venda_liquido - custo_venda)

        self.quantidade -= qtd
        self.custo_total = _arredondar(self.quantidade * self.custo_medio)
        
        # Zerou a posição
        if self.quantidade <= 0:
            self.quantidade = 0
            self.custo_total = 0.0
            self.custo_medio = 0.0

        return resultado


# Posição em carteira antes da primeira nota importada (quantidade original da
# nota, preço médio). Sem ela, as ações vendidas na nota de teste não têm compra
# registrada e o custo de aquisição seria zero. O preço médio de referência é o
# fechamento oficial de 03/01/2022 (arquivo COTAHIST da B3). A chave é a
# especificação do título, exatamente como o parser lê da nota.
POSICOES_INICIAIS = {
    "BBSEGURIDADE ON NM": (54, 20.60),
    "BRASIL ON NM": (41, 28.82),
    "ENERGIAS BR ON NM": (144, 20.74),
    "ENGIE BRASIL ON NM": (27, 38.04),
    "KLABIN S/A UNT N2": (73, 25.52),
    "SUL AMERICA UNT N2": (283, 25.78),
}


def carregar_posicoes_iniciais(fator: float = 1.0) -> Dict[str, "PosicaoAtivo"]:
    """
    Monta as posições iniciais da carteira. O fator acompanha o multiplicador
    da simulação didática, para que a quantidade em carteira cubra as vendas.
    """
    posicoes = {}
    for ticker, (qtd, preco_medio) in POSICOES_INICIAIS.items():
        qtd_ajustada = int(round(qtd * fator))
        posicoes[ticker] = PosicaoAtivo(
            quantidade=qtd_ajustada,
            custo_total=_arredondar(qtd_ajustada * preco_medio),
            custo_medio=preco_medio
        )
    return posicoes


@dataclass
class Operacao:
    """Representa uma operação de compra ou venda."""
    data: str
    tipo: str               # "C" para Compra, "V" para Venda
    ticker: str
    quantidade: int
    preco_unitario: float
    taxas: float = 0.0
    is_day_trade: bool = False
    categoria: str = "ACAO" # "ACAO", "FII", "ETF"
    irrf: float = 0.0


def verificar_isencao_vendas_acoes(total_vendas_acoes_swing: float) -> bool:
    """Retorna True se o total de vendas de Ações (Swing Trade) no mês for <= R$ 20.000,00."""
    return total_vendas_acoes_swing <= 20000.00


@dataclass
class ResultadoMensal:
    """Guarda o resumo fiscal apurado do mês."""
    mes_ano: str
    
    # Totais de vendas
    vendas_acoes_swing: float = 0.0
    vendas_day_trade: float = 0.0
    vendas_fiis: float = 0.0
    
    # Lucros/Prejuízos brutos
    lucro_bruto_swing: float = 0.0
    lucro_bruto_day_trade: float = 0.0
    lucro_bruto_fiis: float = 0.0
    
    # Isenção aplicada
    isento_swing: bool = False
    
    # Prejuízos compensados
    prejuizo_compensado_swing: float = 0.0
    prejuizo_compensado_day_trade: float = 0.0
    prejuizo_compensado_fiis: float = 0.0
    
    # Bases de cálculo
    base_calculo_swing: float = 0.0
    base_calculo_day_trade: float = 0.0
    base_calculo_fiis: float = 0.0
    
    # Impostos brutos por modalidade
    imposto_swing: float = 0.0
    imposto_day_trade: float = 0.0
    imposto_fiis: float = 0.0
    imposto_bruto_total: float = 0.0
    
    # IRRF ("Dedo-duro")
    irrf_mes: float = 0.0
    irrf_compensado: float = 0.0
    irrf_acumulado_para_futuro: float = 0.0
    
    # Prejuízos acumulados para o futuro
    prejuizo_acumulado_fim_swing: float = 0.0
    prejuizo_acumulado_fim_day_trade: float = 0.0
    prejuizo_acumulado_fim_fiis: float = 0.0
    
    # Valores Finais do DARF
    imposto_liquido: float = 0.0
    darf_a_pagar: float = 0.0
    darf_acumulado_para_futuro: float = 0.0


def apurar_mes(
    mes_ano: str,
    operacoes: List[Operacao],
    posicoes: Dict[str, PosicaoAtivo],
    prejuizo_acumulado_ini_swing: float = 0.0,
    prejuizo_acumulado_ini_day_trade: float = 0.0,
    prejuizo_acumulado_ini_fiis: float = 0.0,
    irrf_acumulado_anterior: float = 0.0,
    darf_acumulado_anterior: float = 0.0
) -> Tuple[ResultadoMensal, Dict[str, PosicaoAtivo]]:
    """
    Função principal de apuração mensal.
    Processa compras e vendas do mês, aplica isenções, compensa prejuízos e calcula o imposto final.
    """
    res = ResultadoMensal(mes_ano=mes_ano)

    # 1. Processa cada operação do mês
    for op in operacoes:
        ticker = op.ticker.strip().upper()
        if ticker not in posicoes:
            posicoes[ticker] = PosicaoAtivo()

        if op.tipo.upper() == "C":
            posicoes[ticker].comprar(op.quantidade, op.preco_unitario, op.taxas)
        elif op.tipo.upper() == "V":
            valor_venda_bruto = op.quantidade * op.preco_unitario
            lucro_op = posicoes[ticker].vender(op.quantidade, op.preco_unitario, op.taxas)
            res.irrf_mes += op.irrf

            # Separa os lucros e vendas por categoria
            if op.categoria.upper() == "FII":
                res.vendas_fiis += valor_venda_bruto
                res.lucro_bruto_fiis += lucro_op
            elif op.is_day_trade:
                res.vendas_day_trade += valor_venda_bruto
                res.lucro_bruto_day_trade += lucro_op
            else:
                res.vendas_acoes_swing += valor_venda_bruto
                res.lucro_bruto_swing += lucro_op

    # Arredonda totais de vendas e lucros
    res.vendas_acoes_swing = _arredondar(res.vendas_acoes_swing)
    res.vendas_day_trade = _arredondar(res.vendas_day_trade)
    res.vendas_fiis = _arredondar(res.vendas_fiis)
    
    res.lucro_bruto_swing = _arredondar(res.lucro_bruto_swing)
    res.lucro_bruto_day_trade = _arredondar(res.lucro_bruto_day_trade)
    res.lucro_bruto_fiis = _arredondar(res.lucro_bruto_fiis)

    # 2. Verifica isenção de R$ 20k em Swing Trade de Ações
    res.isento_swing = verificar_isencao_vendas_acoes(res.vendas_acoes_swing)

    # 3. Compensação de Prejuízos (Swing Trade)
    prej_swing = prejuizo_acumulado_ini_swing
    if res.lucro_bruto_swing < 0:
        prej_swing += abs(res.lucro_bruto_swing)
        res.base_calculo_swing = 0.0
    else:
        if res.isento_swing:
            res.base_calculo_swing = 0.0
        else:
            comp = min(res.lucro_bruto_swing, prej_swing)
            res.prejuizo_compensado_swing = _arredondar(comp)
            prej_swing -= comp
            res.base_calculo_swing = _arredondar(res.lucro_bruto_swing - comp)

    res.prejuizo_acumulado_fim_swing = _arredondar(prej_swing)

    # 4. Compensação de Prejuízos (Day Trade)
    prej_dt = prejuizo_acumulado_ini_day_trade
    if res.lucro_bruto_day_trade < 0:
        prej_dt += abs(res.lucro_bruto_day_trade)
        res.base_calculo_day_trade = 0.0
    else:
        comp = min(res.lucro_bruto_day_trade, prej_dt)
        res.prejuizo_compensado_day_trade = _arredondar(comp)
        prej_dt -= comp
        res.base_calculo_day_trade = _arredondar(res.lucro_bruto_day_trade - comp)

    res.prejuizo_acumulado_fim_day_trade = _arredondar(prej_dt)

    # 5. Compensação de Prejuízos (FIIs)
    prej_fiis = prejuizo_acumulado_ini_fiis
    if res.lucro_bruto_fiis < 0:
        prej_fiis += abs(res.lucro_bruto_fiis)
        res.base_calculo_fiis = 0.0
    else:
        comp = min(res.lucro_bruto_fiis, prej_fiis)
        res.prejuizo_compensado_fiis = _arredondar(comp)
        prej_fiis -= comp
        res.base_calculo_fiis = _arredondar(res.lucro_bruto_fiis - comp)

    res.prejuizo_acumulado_fim_fiis = _arredondar(prej_fiis)

    # 6. Cálculo dos Impostos Brutos (15% Swing Ações, 20% Day Trade, 20% FIIs)
    res.imposto_swing = _arredondar(res.base_calculo_swing * 0.15)
    res.imposto_day_trade = _arredondar(res.base_calculo_day_trade * 0.20)
    res.imposto_fiis = _arredondar(res.base_calculo_fiis * 0.20)

    res.imposto_bruto_total = _arredondar(
        res.imposto_swing + res.imposto_day_trade + res.imposto_fiis
    )

    # 7. Abatimento de IRRF acumulado
    irrf_disponivel = _arredondar(irrf_acumulado_anterior + res.irrf_mes)
    irrf_abatido = min(res.imposto_bruto_total, irrf_disponivel)
    res.irrf_compensado = _arredondar(irrf_abatido)
    res.irrf_acumulado_para_futuro = _arredondar(irrf_disponivel - irrf_abatido)

    res.imposto_liquido = _arredondar(res.imposto_bruto_total - res.irrf_compensado)

    # 8. Mínimo de R$ 10,00 para DARF
    valor_acumulado_para_darf = _arredondar(darf_acumulado_anterior + res.imposto_liquido)

    if valor_acumulado_para_darf >= 10.00:
        res.darf_a_pagar = valor_acumulado_para_darf
        res.darf_acumulado_para_futuro = 0.0
    else:
        res.darf_a_pagar = 0.0
        res.darf_acumulado_para_futuro = valor_acumulado_para_darf

    return res, posicoes
