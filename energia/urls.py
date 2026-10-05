from django.urls import path
from core.views import PainelView
app_name = "energia"
urlpatterns = [path("", PainelView.as_view(), name="passo1")]
