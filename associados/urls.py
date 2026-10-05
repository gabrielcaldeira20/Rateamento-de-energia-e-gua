from django.urls import path

from . import views

app_name = "associados"

urlpatterns = [
    path("", views.ListaView.as_view(), name="lista"),
    path("novo/", views.FormularioView.as_view(), name="novo"),
    path("<int:pk>/", views.DetalheView.as_view(), name="detalhe"),
    path("<int:pk>/editar/", views.FormularioView.as_view(), name="editar"),
    path("<int:pk>/inativar/", views.AtivoView.as_view(ativo=False), name="inativar"),
    path("<int:pk>/reativar/", views.AtivoView.as_view(ativo=True), name="reativar"),
    path("<int:pk>/historico/", views.HistoricoAssociadoView.as_view(), name="historico"),
]
