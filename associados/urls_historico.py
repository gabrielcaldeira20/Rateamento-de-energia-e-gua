"""Rotas do histórico de ligações (item próprio no menu)."""
from django.urls import path

from . import views

app_name = "historico"

urlpatterns = [
    path("", views.HistoricoListaView.as_view(), name="lista"),
    path("<int:pk>/editar/", views.HistoricoEditarView.as_view(), name="editar"),
    path("<int:pk>/excluir/", views.HistoricoExcluirView.as_view(), name="excluir"),
]
