from django.urls import path

from . import views

app_name = "despesas"

urlpatterns = [
    path("", views.ListaView.as_view(), name="lista"),
    path("nova/", views.FormularioView.as_view(), name="nova"),
    path("<int:pk>/editar/", views.FormularioView.as_view(), name="editar"),
    path("<int:pk>/excluir/", views.ExcluirView.as_view(), name="excluir"),
]
