import unittest
from utils import (
    PosicaoAtivo,
    Operacao,
    verificar_isencao_vendas_acoes,
    apurar_mes,
    ResultadoMensal,
    classificar_ativo_api
)

class TestUtilsCalculos(unittest.TestCase):

    def test_classificacao_ativo(self):
        # Testa a classificação de FII por final 11 e Ação por final 3/4
        self.assertEqual(classificar_ativo_api("MXRF11"), "FII")
        self.assertEqual(classificar_ativo_api("PETR4"), "ACAO")
        self.assertEqual(classificar_ativo_api("VALE3"), "ACAO")

    def test_custo_medio_e_venda(self):
        pos = PosicaoAtivo()
        
        # Compra 1: 100 @ 30.00 + 5.00 taxas = 3005.00 total -> Custo médio = 30.05
        pos.comprar(100, 30.00, 5.00)
        self.assertEqual(pos.quantidade, 100)
        self.assertEqual(pos.custo_medio, 30.05)
        
        # Compra 2: 100 @ 40.00 + 5.00 taxas = 4005.00 total -> Custo acumulado = 7010.00 / 200 = 35.05
        pos.comprar(100, 40.00, 5.00)
        self.assertEqual(pos.quantidade, 200)
        self.assertEqual(pos.custo_medio, 35.05)
        
        # Venda: 50 @ 50.00 - 5.00 taxas = 2495.00 líquido. Custo = 50 * 35.05 = 1752.50. Lucro = 742.50
        lucro = pos.vender(50, 50.00, 5.00)
        self.assertEqual(pos.quantidade, 150)
        self.assertEqual(pos.custo_medio, 35.05)
        self.assertEqual(lucro, 742.50)

    def test_isencao_20k_acoes_swing(self):
        self.assertTrue(verificar_isencao_vendas_acoes(15000.00))
        self.assertTrue(verificar_isencao_vendas_acoes(20000.00))
        self.assertFalse(verificar_isencao_vendas_acoes(20000.01))

    def test_apuracao_mes_com_isencao(self):
        # Mês com vendas <= R$ 20.000 em ações swing trade (lucro é isento)
        posicoes = {}
        ops = [
            Operacao(data="2026-07-01", tipo="C", ticker="PETR4", quantidade=500, preco_unitario=20.00, taxas=10.00, categoria="ACAO"),
            Operacao(data="2026-07-15", tipo="V", ticker="PETR4", quantidade=500, preco_unitario=30.00, taxas=10.00, categoria="ACAO", irrf=0.75)
        ]
        
        res, pos_fin = apurar_mes(
            mes_ano="2026-07",
            operacoes=ops,
            posicoes=posicoes
        )
        
        self.assertEqual(res.vendas_acoes_swing, 15000.00)
        self.assertTrue(res.isento_swing)
        self.assertEqual(res.base_calculo_swing, 0.0)
        self.assertEqual(res.imposto_bruto_total, 0.0)
        self.assertEqual(res.darf_a_pagar, 0.0)
        # O IRRF do mês isento fica acumulado para uso futuro
        self.assertEqual(res.irrf_acumulado_para_futuro, 0.75)

    def test_apuracao_mes_tributavel_swing_acima_20k(self):
        # Mês com vendas > R$ 20.000 em ações swing trade (lucro tributado a 15%)
        posicoes = {}
        ops = [
            Operacao(data="2026-07-01", tipo="C", ticker="VALE3", quantidade=1000, preco_unitario=50.00, taxas=20.00, categoria="ACAO"),
            # Venda de R$ 60.000 (acima de R$ 20k)
            Operacao(data="2026-07-20", tipo="V", ticker="VALE3", quantidade=1000, preco_unitario=60.00, taxas=20.00, categoria="ACAO", irrf=3.00)
        ]
        
        res, pos_fin = apurar_mes(
            mes_ano="2026-07",
            operacoes=ops,
            posicoes=posicoes
        )
        
        self.assertEqual(res.vendas_acoes_swing, 60000.00)
        self.assertFalse(res.isento_swing)
        # Lucro líquido da operação = (60000 - 20) - (50000 + 20) = 59980 - 50020 = 9960.00
        self.assertEqual(res.lucro_bruto_swing, 9960.00)
        self.assertEqual(res.base_calculo_swing, 9960.00)
        # Imposto bruto = 15% de 9960 = 1494.00
        self.assertEqual(res.imposto_swing, 1494.00)
        # Abatimento de IRRF = 3.00 -> Imposto Líquido = 1491.00
        self.assertEqual(res.imposto_liquido, 1491.00)
        self.assertEqual(res.darf_a_pagar, 1491.00)

    def test_compensacao_prejuizo_e_day_trade_fiis(self):
        posicoes = {}
        # Prejuízo anterior de R$ 500 em swing e R$ 200 em Day Trade
        ops = [
            # Compra e venda FII MXRF11 (não tem isenção)
            Operacao(data="2026-07-05", tipo="C", ticker="MXRF11", quantidade=100, preco_unitario=10.00, taxas=1.00, categoria="FII"),
            Operacao(data="2026-07-10", tipo="V", ticker="MXRF11", quantidade=100, preco_unitario=12.00, taxas=1.00, categoria="FII", irrf=0.10),
            
            # Compra e venda Day Trade Ação
            Operacao(data="2026-07-12", tipo="C", ticker="PETR4", quantidade=100, preco_unitario=30.00, taxas=2.00, is_day_trade=True, categoria="ACAO"),
            Operacao(data="2026-07-12", tipo="V", ticker="PETR4", quantidade=100, preco_unitario=35.00, taxas=2.00, is_day_trade=True, categoria="ACAO", irrf=5.00),
        ]
        
        res, pos_fin = apurar_mes(
            mes_ano="2026-07",
            operacoes=ops,
            posicoes=posicoes,
            prejuizo_acumulado_ini_day_trade=200.00
        )
        
        # Lucro FII = (1200 - 1) - (1000 + 1) = 1199 - 1001 = 198.00. Tax 20% = 39.60
        self.assertEqual(res.lucro_bruto_fiis, 198.00)
        self.assertEqual(res.imposto_fiis, 39.60)
        
        # Lucro Day Trade = (3500 - 2) - (3000 + 2) = 3498 - 3002 = 496.00
        # Com prejuízo anterior de 200 -> Base DT = 296.00. Tax 20% = 59.20
        self.assertEqual(res.lucro_bruto_day_trade, 496.00)
        self.assertEqual(res.prejuizo_compensado_day_trade, 200.00)
        self.assertEqual(res.base_calculo_day_trade, 296.00)
        self.assertEqual(res.imposto_day_trade, 59.20)
        
        # Total Imposto Bruto = 39.60 + 59.20 = 98.80
        # IRRF total = 0.10 + 5.00 = 5.10 -> Imposto Líquido = 93.70
        self.assertEqual(res.imposto_liquido, 93.70)
        self.assertEqual(res.darf_a_pagar, 93.70)

    def test_darf_abaixo_de_10_reais(self):
        # Se o imposto apurado for < R$ 10, não gera DARF e acumula pro próximo mês
        posicoes = {}
        ops = [
            Operacao(data="2026-07-05", tipo="C", ticker="MXRF11", quantidade=10, preco_unitario=10.00, taxas=0.10, categoria="FII"),
            Operacao(data="2026-07-10", tipo="V", ticker="MXRF11", quantidade=10, preco_unitario=12.00, taxas=0.10, categoria="FII", irrf=0.01),
        ]
        
        res, _ = apurar_mes(
            mes_ano="2026-07",
            operacoes=ops,
            posicoes=posicoes
        )
        
        # Lucro = 19.80 -> Imposto 20% = 3.96. Abate IRRF 0.01 = 3.95
        self.assertEqual(res.imposto_liquido, 3.95)
        self.assertEqual(res.darf_a_pagar, 0.0) # < R$ 10.00
        self.assertEqual(res.darf_acumulado_para_futuro, 3.95)

    def test_venda_direta_sem_posicao_previa(self):
        pos = PosicaoAtivo()
        # Venda direta sem ter comprado previamente no objeto (custo médio 0.0)
        # Deve calcular o resultado financeiro sem lançar exceção
        resultado = pos.vender(100, 20.00, 5.00)
        self.assertEqual(resultado, 1995.00)

if __name__ == "__main__":
    unittest.main()
