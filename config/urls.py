from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("associados/", include("associados.urls")),
    path("historico-ligacoes/", include("associados.urls_historico")),
    path("energia/", include("energia.urls")),
    path("cobrancas/", include("cobrancas.urls")),
    path("despesas/", include("despesas.urls")),
    path("relatorios/", include("relatorios.urls")),
    path("", include("core.urls")),
]
