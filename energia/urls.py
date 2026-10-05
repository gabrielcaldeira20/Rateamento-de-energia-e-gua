from django.urls import path

from . import views

app_name = "energia"

urlpatterns = [
    path("", views.Passo1View.as_view(), name="passo1"),
    path("leituras/", views.Passo2View.as_view(), name="passo2"),
    path("revisao/", views.Passo3View.as_view(), name="passo3"),
    path("concluido/", views.ConcluidoView.as_view(), name="concluido"),
    path("cancelar/", views.CancelarView.as_view(), name="cancelar"),
]
