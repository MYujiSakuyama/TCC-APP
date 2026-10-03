"""
app.py - Interface Web em Streamlit para Calculadora de Impostos em Renda Variável (B3)

Este aplicativo foi desenvolvido para o Trabalho de Conclusão de Curso (TCC).
Utiliza o módulo parser.py para leitura de arquivos reais e utils.py para os cálculos fiscais.
Sem dados mockados ou simulados.
"""

import copy
from datetime import datetime

import pandas as pd
import streamlit as st

# Importa os módulos do projeto
from utils import apurar_mes
from parser import ler_arquivo_operacoes, converter_dataframe_para_operacoes

# Colunas padrão de uma planilha de operações
COLUNAS = ["Data", "Tipo", "Ticker", "Quantidade", "Preco", "Taxas", "DayTrade", "IRRF"]

# Colunas que o usuário é obrigado a informar (as demais recebem valor padrão)
COLUNAS_OBRIGATORIAS = ["Data", "Tipo", "Ticker", "Quantidade", "Preco"]

# Configuração da página em modo Wide
st.set_page_config(
    page_title="Calculadora IR Renda Variável (B3)",
    page_icon="📈",
    layout="wide"
)

# Estilização CSS personalizada
st.markdown("""
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    </style>
""", unsafe_allow_html=True)

# Header principal do projeto
st.markdown('<div class="main-header">📉 Calculadora de Imposto de Renda em Renda Variável (B3)</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Trabalho de Conclusão de Curso (TCC) - Instituto Federal do Paraná (IFPR Campus Londrina)</div>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES
# -----------------------------------------------------------------------------
def formatar_brl(valor: float) -> str:
    """Formata um número no padrão monetário brasileiro (R$ 1.234,56)."""
    return f"R$ {valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def df_vazio() -> pd.DataFrame:
    """Cria um DataFrame vazio com as colunas padrão de operações."""
    return pd.DataFrame(columns=COLUNAS)


def preparar_operacoes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Valida as colunas obrigatórias, converte a coluna 'Data' para data real,
    adiciona a coluna 'Mes' (AAAA-MM) e ordena as operações em ordem cronológica.

    A ordem cronológica é indispensável: o custo médio de cada ativo depende
    da sequência em que as compras e as vendas aconteceram.
    """
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError("O arquivo não possui as colunas obrigatórias: " + ", ".join(faltando))

    df = df.copy()
    df["Data"] = pd.to_datetime(df["Data"], format="mixed", dayfirst=True, errors="coerce")

    # Descarta linhas sem data válida (cabeçalhos e rodapés captados pelo parser)
    df = df.dropna(subset=["Data"])
    if df.empty:
        raise ValueError("Nenhuma operação com data válida foi encontrada no arquivo.")

    df["Mes"] = df["Data"].dt.strftime("%Y-%m")
    return df.sort_values("Data").reset_index(drop=True)


# -----------------------------------------------------------------------------
# SIDEBAR: Configuração de Saldos de Meses Anteriores (Reais)
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ Saldos de Meses Anteriores")
st.sidebar.caption("Saldos existentes antes do primeiro mês importado.")

prej_ini_swing = st.sidebar.number_input("Prejuízo Acumulado (Swing Trade Ações)", min_value=0.0, value=0.0, step=50.0)
prej_ini_dt = st.sidebar.number_input("Prejuízo Acumulado (Day Trade)", min_value=0.0, value=0.0, step=50.0)
prej_ini_fiis = st.sidebar.number_input("Prejuízo Acumulado (FIIs)", min_value=0.0, value=0.0, step=50.0)
irrf_anterior = st.sidebar.number_input("IRRF Retido Acumulado Anterior", min_value=0.0, value=0.0, step=1.0)
darf_anterior = st.sidebar.number_input("DARF Acumulado Anterior (< R$ 10,00)", min_value=0.0, value=0.0, step=1.0)

# Inicializa o estado de sessão para armazenar as operações do usuário
if "df_operacoes" not in st.session_state:
    st.session_state["df_operacoes"] = df_vazio()

if "mapa_categorias" not in st.session_state:
    st.session_state["mapa_categorias"] = {}

# -----------------------------------------------------------------------------
# TABS PRINCIPAIS
# -----------------------------------------------------------------------------
tab_import, tab_apuracao, tab_docs = st.tabs([
    "📥 1. Entrada de Operações (Parser)",
    "📊 2. Apuração e Relatório",
    "📚 3. Regras de Cálculo (TCC)"
])

# -----------------------------------------------------------------------------
# TAB 1: Parser de Arquivos Reais e Lançamento Manual
# -----------------------------------------------------------------------------
with tab_import:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Upload de Arquivo Real (PDF, CSV ou Excel)")
        uploaded_file = st.file_uploader(
            "Selecione a Nota de Corretagem (.pdf) ou planilha (.csv / .xlsx)",
            type=["pdf", "csv", "xlsx"]
        )

        if uploaded_file is not None:
            try:
                # Utiliza o parser.py separado para importar os dados reais
                df_parsed = ler_arquivo_operacoes(uploaded_file, uploaded_file.name)
                if df_parsed.empty:
                    st.warning(
                        f"Nenhuma operação foi identificada em '{uploaded_file.name}'. "
                        "Confira o arquivo ou lance as operações manualmente."
                    )
                else:
                    # Valida o conteúdo antes de gravar no estado da sessão
                    preparar_operacoes(df_parsed)
                    st.session_state["df_operacoes"] = df_parsed
                    st.success(
                        f"Arquivo '{uploaded_file.name}' importado com sucesso via parser.py "
                        f"({len(df_parsed)} operações)."
                    )
            except Exception as e:
                st.error(f"Erro no parsing do arquivo: {e}")

    with col2:
        st.subheader("Adicionar Operação Manualmente")
        with st.form("form_operacao"):
            form_data = st.date_input("Data da Operação", datetime.now())
            form_tipo = st.selectbox("Tipo de Operação", ["C (Compra)", "V (Venda)"])
            form_ticker = st.text_input("Ticker (Ex: PETR4, MXRF11)")
            form_qtd = st.number_input("Quantidade", min_value=1, value=100, step=1)
            form_preco = st.number_input("Preço Unitário (R$)", min_value=0.01, value=10.00, step=1.0)
            form_taxas = st.number_input("Taxas / Corretagem (R$)", min_value=0.0, value=0.0, step=0.5)
            form_dt = st.checkbox("Operação Day Trade?")
            form_irrf = st.number_input("IRRF Retido (R$)", min_value=0.0, value=0.0, step=0.1)

            btn_adicionar = st.form_submit_button("Adicionar Operação")

        if btn_adicionar:
            ticker_informado = form_ticker.strip().upper()
            if not ticker_informado:
                st.warning("Por favor, preencha o código do ticker.")
            else:
                nova_op = {
                    "Data": str(form_data),
                    "Tipo": "C" if "Compra" in form_tipo else "V",
                    "Ticker": ticker_informado,
                    "Quantidade": int(form_qtd),
                    "Preco": float(form_preco),
                    "Taxas": float(form_taxas),
                    "DayTrade": bool(form_dt),
                    "IRRF": float(form_irrf)
                }
                st.session_state["df_operacoes"] = pd.concat(
                    [st.session_state["df_operacoes"], pd.DataFrame([nova_op])],
                    ignore_index=True
                )
                st.success(f"Operação com {ticker_informado} adicionada!")

    st.divider()
    st.subheader("📋 Operações Importadas / Cadastradas")

    if not st.session_state["df_operacoes"].empty:
        st.dataframe(st.session_state["df_operacoes"], width="stretch")
        if st.button("Limpar Operações"):
            st.session_state["df_operacoes"] = df_vazio()
            st.session_state["mapa_categorias"] = {}
            st.rerun()
    else:
        st.info("Nenhuma operação cadastrada. Faça upload de um arquivo ou adicione uma operação manualmente.")

# -----------------------------------------------------------------------------
# TAB 2: Apuração Fiscal Real
# -----------------------------------------------------------------------------
with tab_apuracao:
    if st.session_state["df_operacoes"].empty:
        st.warning("Nenhuma operação encontrada. Importe ou adicione operações na Aba 1.")
    else:
        st.subheader("🔍 Classificação de Ativos e Apuração Fiscal")

        try:
            df_ops = preparar_operacoes(st.session_state["df_operacoes"])

            # Apura mês a mês, em ordem cronológica, levando para o mês seguinte
            # as posições, os prejuízos, o IRRF e o DARF que sobraram.
            with st.spinner("Classificando ativos via API de dados externa e apurando os meses..."):
                posicoes = {}
                prej_swing, prej_dt, prej_fiis = prej_ini_swing, prej_ini_dt, prej_ini_fiis
                irrf_acum, darf_acum = irrf_anterior, darf_anterior
                resultados = {}
                posicoes_por_mes = {}

                for mes in sorted(df_ops["Mes"].unique()):
                    operacoes_mes = converter_dataframe_para_operacoes(
                        df_ops[df_ops["Mes"] == mes],
                        st.session_state["mapa_categorias"]
                    )
                    res, posicoes = apurar_mes(
                        mes_ano=mes,
                        operacoes=operacoes_mes,
                        posicoes=posicoes,
                        prejuizo_acumulado_ini_swing=prej_swing,
                        prejuizo_acumulado_ini_day_trade=prej_dt,
                        prejuizo_acumulado_ini_fiis=prej_fiis,
                        irrf_acumulado_anterior=irrf_acum,
                        darf_acumulado_anterior=darf_acum
                    )

                    # Os saldos apurados viram os saldos iniciais do próximo mês
                    prej_swing = res.prejuizo_acumulado_fim_swing
                    prej_dt = res.prejuizo_acumulado_fim_day_trade
                    prej_fiis = res.prejuizo_acumulado_fim_fiis
                    irrf_acum = res.irrf_acumulado_para_futuro
                    darf_acum = res.darf_acumulado_para_futuro

                    resultados[mes] = res
                    posicoes_por_mes[mes] = copy.deepcopy(posicoes)
        except Exception as e:
            st.error(f"Não foi possível apurar as operações: {e}")
            st.stop()

        meses = list(resultados.keys())
        mes_selecionado = st.selectbox(
            "Mês de apuração",
            meses,
            index=len(meses) - 1,
            help="Os meses anteriores são sempre processados antes, para manter o custo médio e os saldos corretos."
        )
        res_mensal = resultados[mes_selecionado]
        posicoes_finais = posicoes_por_mes[mes_selecionado]

        # Métricas de Destaque
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Vendas Swing (Ações)", formatar_brl(res_mensal.vendas_acoes_swing))
        c2.metric("Isenção R$ 20k Aplicada?", "SIM (Isento)" if res_mensal.isento_swing else "NÃO (Tributado)")
        c3.metric("Imposto Bruto Apurado", formatar_brl(res_mensal.imposto_bruto_total))
        c4.metric("DARF Final a Pagar", formatar_brl(res_mensal.darf_a_pagar))

        st.divider()

        # Detalhamento por Modalidade
        col_res1, col_res2 = st.columns(2)

        with col_res1:
            st.markdown("### 📊 Detalhamento por Modalidade")
            dados_resumo = [
                {"Modalidade": "Swing Trade (Ações)", "Vendas (R$)": res_mensal.vendas_acoes_swing, "Lucro Bruto (R$)": res_mensal.lucro_bruto_swing, "Prej. Compensado": res_mensal.prejuizo_compensado_swing, "Base de Cálculo": res_mensal.base_calculo_swing, "Alíquota": "15%", "Imposto Bruto": res_mensal.imposto_swing},
                {"Modalidade": "Day Trade (Ações/ETFs)", "Vendas (R$)": res_mensal.vendas_day_trade, "Lucro Bruto (R$)": res_mensal.lucro_bruto_day_trade, "Prej. Compensado": res_mensal.prejuizo_compensado_day_trade, "Base de Cálculo": res_mensal.base_calculo_day_trade, "Alíquota": "20%", "Imposto Bruto": res_mensal.imposto_day_trade},
                {"Modalidade": "FIIs (Fundos Imobiliários)", "Vendas (R$)": res_mensal.vendas_fiis, "Lucro Bruto (R$)": res_mensal.lucro_bruto_fiis, "Prej. Compensado": res_mensal.prejuizo_compensado_fiis, "Base de Cálculo": res_mensal.base_calculo_fiis, "Alíquota": "20%", "Imposto Bruto": res_mensal.imposto_fiis},
            ]
            st.dataframe(pd.DataFrame(dados_resumo), width="stretch")

        with col_res2:
            st.markdown("### 🧾 Resumo de Deduções e Saldo Final")
            st.write(f"• **IRRF Retido no Mês:** {formatar_brl(res_mensal.irrf_mes)}")
            st.write(f"• **IRRF Total Compensado:** {formatar_brl(res_mensal.irrf_compensado)}")
            st.write(f"• **IRRF Acumulado para Futuro:** {formatar_brl(res_mensal.irrf_acumulado_para_futuro)}")
            st.write(f"• **Imposto Líquido Devido:** {formatar_brl(res_mensal.imposto_liquido)}")
            st.write(f"• **Saldo Prejuízo Swing Trade Futuro:** {formatar_brl(res_mensal.prejuizo_acumulado_fim_swing)}")
            st.write(f"• **Saldo Prejuízo Day Trade Futuro:** {formatar_brl(res_mensal.prejuizo_acumulado_fim_day_trade)}")
            st.write(f"• **Saldo Prejuízo FIIs Futuro:** {formatar_brl(res_mensal.prejuizo_acumulado_fim_fiis)}")

            if res_mensal.darf_a_pagar > 0:
                st.success(f"✅ **GERAR DARF NO VALOR DE {formatar_brl(res_mensal.darf_a_pagar)}**")
            else:
                st.info(
                    "ℹ️ **SEM DARF A PAGAR ESTE MÊS.** Valor acumulado para futuro: "
                    f"{formatar_brl(res_mensal.darf_acumulado_para_futuro)}"
                )

        st.divider()

        # Consolidado de todos os meses apurados
        if len(meses) > 1:
            st.markdown("### 🗓️ Consolidado dos Meses Apurados")
            st.dataframe(pd.DataFrame([
                {
                    "Mês": r.mes_ano,
                    "Imposto Bruto": r.imposto_bruto_total,
                    "IRRF Compensado": r.irrf_compensado,
                    "Imposto Líquido": r.imposto_liquido,
                    "DARF a Pagar": r.darf_a_pagar
                }
                for r in resultados.values()
            ]), width="stretch")
            st.divider()

        # Posição Atualizada da Carteira
        st.markdown(f"### 💼 Posição da Carteira ao Final de {mes_selecionado} (Custo Médio)")
        dados_pos = [
            {
                "Ticker": ticker,
                "Categoria": st.session_state["mapa_categorias"].get(ticker, "ACAO"),
                "Quantidade em Carteira": pos.quantidade,
                "Custo Médio Unitário (R$)": formatar_brl(pos.custo_medio),
                "Custo Total Acumulado (R$)": formatar_brl(pos.custo_total)
            }
            for ticker, pos in sorted(posicoes_finais.items())
            if pos.quantidade > 0
        ]
        if dados_pos:
            st.dataframe(pd.DataFrame(dados_pos), width="stretch")
        else:
            st.info("Nenhum ativo em carteira ao final do mês selecionado (todas as posições foram zeradas).")

        # Exportar Relatório Real
        relatorio_txt = f"""
====================================================================
RELATÓRIO FISCAL DE IMPOSTOS EM RENDA VARIÁVEL (B3) - TCC IFPR
====================================================================
Mês Apurado: {res_mensal.mes_ano}

1. VOLUMES DE VENDAS
- Swing Trade (Ações): {formatar_brl(res_mensal.vendas_acoes_swing)}
- Day Trade: {formatar_brl(res_mensal.vendas_day_trade)}
- Fundos Imobiliários (FIIs): {formatar_brl(res_mensal.vendas_fiis)}

2. APURAÇÃO DE LUCROS E IMPOSTOS
- Lucro Isento (Swing Trade <= 20k): {'SIM' if res_mensal.isento_swing else 'NÃO'}
- Imposto Bruto Swing Trade (15%): {formatar_brl(res_mensal.imposto_swing)}
- Imposto Bruto Day Trade (20%): {formatar_brl(res_mensal.imposto_day_trade)}
- Imposto Bruto FIIs (20%): {formatar_brl(res_mensal.imposto_fiis)}
- IMPOSTO BRUTO TOTAL: {formatar_brl(res_mensal.imposto_bruto_total)}

3. DEDUÇÕES E DARF
- IRRF Compensado: {formatar_brl(res_mensal.irrf_compensado)}
- IMPOSTO LÍQUIDO DEVIDO: {formatar_brl(res_mensal.imposto_liquido)}
- VALOR DO DARF A PAGAR: {formatar_brl(res_mensal.darf_a_pagar)}
- VALOR ACUMULADO PARA FUTURO (< R$ 10,00): {formatar_brl(res_mensal.darf_acumulado_para_futuro)}

4. SALDOS DE PREJUÍZO A COMPENSAR NO FUTURO
- Swing Trade (Ações): {formatar_brl(res_mensal.prejuizo_acumulado_fim_swing)}
- Day Trade: {formatar_brl(res_mensal.prejuizo_acumulado_fim_day_trade)}
- Fundos Imobiliários (FIIs): {formatar_brl(res_mensal.prejuizo_acumulado_fim_fiis)}
====================================================================
"""
        st.download_button(
            label="📄 Baixar Relatório Fiscal (.txt)",
            data=relatorio_txt,
            file_name=f"relatorio_fiscal_{res_mensal.mes_ano}.txt",
            mime="text/plain"
        )

# -----------------------------------------------------------------------------
# TAB 3: Documentação das Regras (TCC)
# -----------------------------------------------------------------------------
with tab_docs:
    st.subheader("📚 Regras de Tributação em Renda Variável (B3)")
    st.markdown("""
    Este sistema realiza o cálculo dos impostos conforme a legislação da **Receita Federal do Brasil (RFB)**:

    1. **Isenção de R$ 20.000,00 (Swing Trade Ações)**: Vendas totais de ações no mês de até R$ 20k possuem lucro isento de IR.
    2. **Alíquotas de Imposto**: 15% para Swing Trade de Ações/ETFs; 20% para Day Trade e cotas de FIIs.
    3. **Compensação de Prejuízos**: Prejuízos acumulados anteriores compensam lucros da mesma modalidade.
    4. **Dedução de IRRF**: Imposto de renda retido na fonte (dedo-duro) é abatido do imposto devido.
    5. **Mínimo de R$ 10,00 para DARF**: Imposto a recolher inferior a R$ 10,00 acumula para meses futuros.
    6. **Custo Médio Ponderado**: O custo de cada ativo é recalculado a cada compra, em ordem cronológica.

    **Formato esperado da planilha (CSV / Excel)**

    | Coluna | Obrigatória | Exemplo |
    | --- | --- | --- |
    | `Data` | Sim | `15/07/2026` ou `2026-07-15` |
    | `Tipo` | Sim | `C` (compra) ou `V` (venda) |
    | `Ticker` | Sim | `PETR4`, `MXRF11` |
    | `Quantidade` | Sim | `100` |
    | `Preco` | Sim | `30.50` |
    | `Taxas` | Não (padrão `0`) | `4.85` |
    | `DayTrade` | Não (padrão `False`) | `Sim` / `Não` |
    | `IRRF` | Não (padrão `0`) | `0.75` |
    """)
