from django.urls import reverse

# Itens do menu lateral. Os bloqueados são só visuais, como no protótipo.
MENU = [
    ("Painel", "core:painel", "bi-speedometer2"),
    ("Associados", "associados:lista", "bi-people"),
    ("Lançamento de Energia", "energia:passo1", "bi-lightning-charge"),
    ("Cobranças", "cobrancas:lista", "bi-receipt"),
    ("Despesas", "despesas:lista", "bi-wallet2"),
    ("Relatório Financeiro", "relatorios:financeiro", "bi-bar-chart"),
    ("Configurações", "core:configuracoes", "bi-gear"),
]
MENU_BLOQUEADO = [
    ("PIX automático", "bi-qr-code", "Completo"),
    ("Histórico de ligações", "bi-clock-history", "Completo"),
]


def menu(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    itens = []
    for rotulo, nome_url, icone in MENU:
        url = reverse(nome_url)
        ativo = request.path == url if url == "/" else request.path.startswith(url)
        itens.append({"rotulo": rotulo, "url": url, "icone": icone, "ativo": ativo})
    bloqueados = [{"rotulo": r, "icone": i, "plano": p} for r, i, p in MENU_BLOQUEADO]
    return {"menu_itens": itens, "menu_bloqueados": bloqueados}
