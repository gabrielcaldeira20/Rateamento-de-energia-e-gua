from django.urls import reverse

# Itens do menu lateral.
MENU = [
    ("Painel", "core:painel", "bi-speedometer2"),
    ("Associados", "associados:lista", "bi-people"),
    ("Histórico de ligações", "historico:lista", "bi-clock-history"),
    ("Lançamento de Energia", "energia:passo1", "bi-lightning-charge"),
    ("Cobranças", "cobrancas:lista", "bi-receipt"),
    ("Despesas", "despesas:lista", "bi-wallet2"),
    ("Relatório Financeiro", "relatorios:financeiro", "bi-bar-chart"),
    ("Configurações", "core:configuracoes", "bi-gear"),
]


def menu(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    itens = []
    for rotulo, nome_url, icone in MENU:
        url = reverse(nome_url)
        ativo = request.path == url if url == "/" else request.path.startswith(url)
        itens.append({"rotulo": rotulo, "url": url, "icone": icone, "ativo": ativo})
    return {"menu_itens": itens}
