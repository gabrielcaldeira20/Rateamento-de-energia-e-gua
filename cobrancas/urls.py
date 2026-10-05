from django.urls import path

from . import views

app_name = "cobrancas"

urlpatterns = [
    path("", views.ListaView.as_view(), name="lista"),
    path("<int:pk>/pagar/", views.PagarView.as_view(), name="pagar"),
    path("lote/", views.LoteView.as_view(), name="lote"),
    path("gerar-mensais/", views.GerarMensaisView.as_view(), name="gerar_mensais"),
]
