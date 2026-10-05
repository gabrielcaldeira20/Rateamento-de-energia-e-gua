from django.urls import path
from core.views import PainelView
app_name = "relatorios"
urlpatterns = [path("financeiro/", PainelView.as_view(), name="financeiro")]
