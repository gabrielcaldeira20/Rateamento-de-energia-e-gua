from django.urls import path

from . import views

app_name = "relatorios"

urlpatterns = [
    path("financeiro/", views.FinanceiroView.as_view(), name="financeiro"),
]
