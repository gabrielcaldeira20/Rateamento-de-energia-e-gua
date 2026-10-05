from django.urls import path
from core.views import PainelView
app_name = "cobrancas"
urlpatterns = [path("", PainelView.as_view(), name="lista")]
