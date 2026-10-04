# Calculadora de Imposto de Renda em Renda Variável (B3)

Aplicação Web desenvolvida em **Python** e **Streamlit** para apuração fiscal e cálculo automatizado de Imposto de Renda (IR) incidente sobre operações no mercado financeiro brasileiro (B3), desenvolvida como projeto de Trabalho de Conclusão de Curso (TCC) no **Instituto Federal do Paraná (IFPR - Campus Londrina)**.

---

## Principais Funcionalidades

- **Importação Automática (Parser)**:
  - Leitura e extração de dados reais a partir de **Notas de Corretagem em PDF** (Padrão SINACOR B3).
  - Possibilidade de lançamento manual de operações.

- **Simulação Didática (Multiplicador 2x para TCC)**:
  - Módulo para ajustar a escala das operações da nota de teste (`multiplicador.py`).
  - Como a nota real de teste possui volume de vendas em torno de R$ 15.801,54 (ficando isenta pela faixa de R$ 20.000,00 da RFB), o multiplicador dobra as operações para ~R$ 31.603,08, permitindo demonstrar a tributação efetiva (15%), deduções de IRRF e emissão de DARF.
  - Alternância imediata entre o modo original (1x - Isento) e o modo de demonstração (2x - Tributado) via interface Streamlit.

- **Apuração Fiscal e Regras da Receita Federal (RFB)**:
  - **Custo Médio Ponderado**: Recálculo dinâmico da posição da carteira a cada nova compra cronológica.
  - **Isenção dos R$ 20.000,00**: Aplicação automática do benefício de isenção de IR para alienações de ações em operações comuns (Swing Trade).
  - **Segregação por Modalidade**:
    - **Swing Trade (Ações/ETFs)**: Alíquota de 15%.
    - **Day Trade**: Alíquota de 20%.
    - **Fundos Imobiliários (FIIs)**: Alíquota de 20% (sem isenção de 20k).
  - **Compensação de Prejuízos**: Abatimento de perdas acumuladas em meses anteriores exclusivamente dentro da mesma categoria operacional.
  - **Dedução de IRRF**: Compensação do imposto retido na fonte ("dedo-duro").
  - **Regra Mínima de DARF**: Cumprimento da regra de valor mínimo de R$ 10,00 para recolhimento mensal (acumulação automática para meses futuros).

- **Relatório e Exportação**:
  - Visualização detalhada do demonstrativo mensal.
  - Download do relatório fiscal consolidado em formato `.txt`.
  - Posição final da carteira e custos médios por ativo.

---

## Estrutura do Repositório

```text
├── app.py           # Interface web e dashboard Streamlit
├── parser.py        # Módulo de extração e parsing de notas em PDF (padrão SINACOR)
├── multiplicador.py # Módulo de simulação didática (multiplicador 2x para TCC)
├── utils.py         # Módulo de regras de negócio, cálculos fiscais e apuração
├── test_utils.py    # Testes unitários das regras de cálculo e simulação
├── requirements.txt # Dependências do projeto
└── README.md        # Documentação do projeto
```

---

## Como Executar Localmente

1. **Clone o repositório:**
   ```bash
   git clone https://github.com/MYujiSakuyama/TCC-APP.git
   cd TCC-APP
   ```

2. **Crie e ative um ambiente virtual (opcional, mas recomendado):**
   ```bash
   python -m venv .venv
   # No Windows:
   .venv\Scripts\activate
   # No Linux/macOS:
   source .venv/bin/activate
   ```

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Execute a aplicação Streamlit:**
   ```bash
   streamlit run app.py
   ```

---

## Executando os Testes Unitários

Para validar a integridade dos cálculos fiscais e regras de negócio:

```bash
python -m unittest test_utils.py
```
