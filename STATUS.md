# Status da construção

Só fica marcado como pronto o que tem teste automatizado passando.
Para rodar os testes: `DEBUG=True python manage.py test` (128 testes, todos passando).

| Fase | Item | Status | Testes |
|---|---|---|---|
| 1 | Esqueleto, login real, Configuração, template base | [x] pronto | core/tests.py |
| 2 | Associados | [x] pronto | associados/tests.py |
| 3 | Energia: 3 passos, rateio, disponibilidade, multa, validações | [x] pronto | energia/tests.py |
| 4 | Cobranças: geração mensal, pagamentos, parcial, crédito, baixa em lote | [x] pronto | cobrancas/tests.py |
| 5 | Despesas e painel inicial | [x] pronto | despesas/tests.py |
| 6 | Lembrete pelo WhatsApp | [x] pronto | cobrancas/tests.py (WhatsAppTests) |
| 7 | Relatório financeiro | [x] pronto | relatorios/tests.py |
| 8 | Entrega: requirements, .env.example, README | [x] pronto | core/tests_entrega.py |
| 8 | Comandos exportar_dados e importar_planilhas | [x] pronto | core/tests_entrega.py |
| 9 | Histórico de ligações: modelo, migração com carga, situacao_em, formulário | [x] pronto | associados/tests_historico.py |
| 9 | Histórico de ligações: telas e item de menu | [x] pronto | associados/tests_historico.py (TelasHistoricoTests) |
| 9 | Histórico de ligações no rateio e na geração mensal | [x] pronto | associados/tests_historico.py (UsoNoRateioENaGeracaoTests) |
| 9 | Migração do histórico: aplica e reverte com e sem dados | [x] pronto | associados/tests_historico.py (MigracaoTests) |
| 10 | Exportação do relatório em CSV | [x] pronto | relatorios/tests_exportacao.py |
| 10 | Exportação do relatório em PDF | [x] pronto | relatorios/tests_exportacao.py |
| 11 | Importação da planilha oficial (importar_associados) | [x] pronto | associados/tests_importacao.py |
| 11 | Deploy em VPS: Docker, Caddy, backup e restauração | [x] testado no Docker local em 11/11/2026 | manual, roteiro no README |

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

- **Testes automatizados no PostgreSQL:** a suíte roda em SQLite. O sistema já rodou contra
  PostgreSQL 16 e gunicorn no Docker local (migrações, importação dos 65 associados, backup e
  restauração), mas a suíte de testes ainda não foi executada contra o PostgreSQL.
- **Servidor real:** o deploy foi testado só no Docker local, com o certificado próprio do Caddy.
  O certificado da Let's Encrypt, o cron do backup e a cópia externa só se verificam no VPS.

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

### Histórico de ligações e exportação do relatório

17. O histórico fica no app de associados. A lista geral tem rota própria, `/historico-ligacoes/`.
18. Datas no futuro são recusadas, no formulário do associado e no histórico.
19. Na edição do associado, só os serviços que mudaram geram registro, com a data informada.
    Se já houver registro mais recente, ele continua valendo e o estado atual não muda.
20. Editar um registro para uma data que já tem registro do mesmo serviço é recusado, com aviso.
    Criar um registro nessa data atualiza o existente, como pede a regra de não duplicar.
21. Ligar uma rede pelo histórico pede a leitura inicial quando o associado ainda não tem uma.
22. O padrão ligado não tem histórico. No rateio de uma competência, ele só é exigido de quem continua com a rede hoje.
    Quem desligou a rede depois da competência entra pelo histórico. Associados inativos continuam fora do rateio.
23. No admin, rede da Sede, rede do Poço e água ficam somente leitura, porque são reflexo do histórico.
24. Os associados importados por `importar_planilhas` recebem a data do dia da importação no histórico.
25. Exportação sem início ou fim válidos usa os últimos 6 meses, o mesmo padrão da tela.
    Formato diferente de pdf ou csv responde com erro 400.
26. O CSV traz cabeçalho (associação, regime, período, data de geração), resumo e as duas tabelas, com uma linha de total em cada.
    As tabelas da exportação vêm em ordem de data crescente. Na tela, a ordem é decrescente.
27. O PDF não tem gráfico, que era opcional. Ele sai sem compressão de página, o que deixa o arquivo um pouco maior.
