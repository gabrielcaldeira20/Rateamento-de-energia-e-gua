# Status da construção

Só fica marcado como pronto o que tem teste automatizado passando.
Para rodar os testes: `DEBUG=True python manage.py test`.

| Fase | Item | Status | Testes |
|---|---|---|---|
| 1 | Esqueleto, login real, Configuração, template base | [x] pronto | core/tests.py |
| 2 | Associados | [x] pronto | associados/tests.py |
| 3 | Energia: 3 passos, rateio, disponibilidade, multa, validações | [x] pronto | energia/tests.py |
| 4 | Cobranças: geração mensal, pagamentos, parcial, crédito, baixa em lote | [x] pronto | cobrancas/tests.py |
| 5 | Despesas e painel inicial | [ ] | |
| 6 | Lembrete pelo WhatsApp | [ ] | |
| 7 | Relatório financeiro | [ ] | |
| 8 | Entrega: requirements, build.sh, .env.example, README do Render | [ ] | |
