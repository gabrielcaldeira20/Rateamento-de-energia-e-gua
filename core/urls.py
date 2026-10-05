from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.PainelView.as_view(), name="painel"),
    path("configuracoes/", views.ConfiguracoesView.as_view(), name="configuracoes"),
]
