# Status da construção

Só fica marcado como pronto o que tem teste automatizado passando.
Para rodar os testes: `DEBUG=True python manage.py test` (73 testes, todos passando).

| Fase | Item | Status | Testes |
|---|---|---|---|
| 1 | Esqueleto, login real, Configuração, template base | [x] pronto | core/tests.py |
| 2 | Associados | [x] pronto | associados/tests.py |
| 3 | Energia: 3 passos, rateio, disponibilidade, multa, validações | [x] pronto | energia/tests.py |
| 4 | Cobranças: geração mensal, pagamentos, parcial, crédito, baixa em lote | [x] pronto | cobrancas/tests.py |
| 5 | Despesas e painel inicial | [x] pronto | despesas/tests.py |
| 6 | Lembrete pelo WhatsApp | [x] pronto | cobrancas/tests.py (WhatsAppTests) |
| 7 | Relatório financeiro | [x] pronto | relatorios/tests.py |
| 8 | Entrega: requirements, build.sh, .env.example, README do Render | [x] pronto | core/tests_entrega.py |
| 8 | Comandos exportar_dados e importar_planilhas | [x] pronto | core/tests_entrega.py |

## Testes obrigatórios

| Regra | Teste |
|---|---|
| Rateio: soma e arredondamento | `energia.tests.CalculosTests` |
| Multa: 100 kWh não gera, 101 gera | `energia.tests.FechamentoTests.test_multa_100_kwh_nao_gera_e_101_gera` |
| Disponibilidade R$ 10 com duas redes, zero para a Associação | `energia.tests.FechamentoTests.test_disponibilidade_10_reais_com_duas_redes_e_zero_para_associacao` |
| Gerar mensais duas vezes sem duplicar | `cobrancas.tests.GeracaoMensalTests.test_gerar_duas_vezes_nao_duplica` |
| Pagamento parcial e a maior | `cobrancas.tests.PagamentoTests` |
| Fechamento duplicado e leitura menor bloqueados | `energia.tests.FechamentoTests` |
| Baixa em lote atômica e pelo saldo restante | `cobrancas.tests.BaixaEmLoteTests` |

## Não verificado nesta máquina

- **PostgreSQL:** não há PostgreSQL instalado. Os testes rodaram em SQLite. As restrições do banco
  usam só recursos padrão do Django, mas a primeira rodada contra PostgreSQL deve ser feita no Render
  ou com `DATABASE_URL` apontando para um PostgreSQL local.
- **Gunicorn:** não roda no Windows. A configuração de produção foi conferida com `check --deploy`
  e `collectstatic` com `DEBUG=False`.

## Escolhas onde nem as instruções nem o protótipo decidiam

1. Leituras de medidor e kWh são números inteiros, como no protótipo (campo com passo 1).
2. A leitura inicial pode ser zero. Ela só é obrigatória quando a rede está marcada.
3. "Leitura zerada" é consumo de 0 kWh (leitura atual igual à anterior). Só gera aviso.
4. A multa tem a mesma rede e o mesmo vencimento da energia que a gerou. Quem passa do limite nas duas redes recebe duas multas.
5. Não se cria cobrança de valor zero, como no protótipo. A Associação sem consumo fica só com a leitura gravada.
6. O pagamento grava o valor recebido inteiro. A cobrança registra no máximo o próprio valor, e o excedente vira crédito.
   As entradas do relatório somam o valor recebido, inclusive o excedente.
7. A baixa em lote usa a data de hoje, como no protótipo, e ignora cobranças já pagas.
8. No relatório por data de pagamento, as despesas entram pela data. Por competência, entram pela competência.
9. A taxa de disponibilidade do relatório soma as cobranças de energia com competência no período, nos dois modos.
10. O período personalizado do relatório é escolhido por mês, como no protótipo.
11. A despesa tem data e competência. Se a competência ficar vazia, usa o mês da data.
12. Telefone com 10 ou 11 dígitos sempre recebe o prefixo 55, inclusive números do DDD 55.
    Com 12 ou mais dígitos começando por 55, fica como está. Menos de 10 dígitos é tratado como sem telefone.
13. O link do WhatsApp só existe para cobranças em aberto. Sem chave PIX cadastrada, a tela de cobranças mostra um aviso.
14. A geração mensal escolhe o mês num campo, com o mês atual como padrão.
15. Os passos do lançamento de energia guardam os dados na sessão até a confirmação.
16. A exportação de dados inclui também as leituras, que fazem parte dos fechamentos.
