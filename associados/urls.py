from django.urls import path
from core.views import PainelView
app_name = "associados"
urlpatterns = [path("", PainelView.as_view(), name="lista")]
