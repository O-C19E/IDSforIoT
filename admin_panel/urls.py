from django.urls import path

from .views import (
    get_light_status,
    request_access,
    server_dashboard,
    toggle_all_lights,
    toggle_light,
)

urlpatterns = [
    path("lights/all/", toggle_all_lights),
    path("status/<uuid:cust_id>/", get_light_status),
    path("request-access", request_access),
    path("api/toggle-light", toggle_light),
    path("server/", server_dashboard),
]
