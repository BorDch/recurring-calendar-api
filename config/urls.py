"""Calendar routes and profile-dependent access policy."""

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from events import views


def calendar_view(view):
    """Local demo permits anonymous calls; other profiles require login and CSRF."""

    if settings.CALENDAR_PROFILE in ("private", "production"):
        return login_required(view)
    return csrf_exempt(view)


urlpatterns = [
    path("", calendar_view(views.calendar_home), name="calendar_home"),
    path("admin/", admin.site.urls),
    path("events/range/", calendar_view(views.events_range), name="events_range"),
    path("add/", calendar_view(views.add_event), name="add_event"),
    path(
        "events/<str:year>/<str:month>/<str:day>/",
        calendar_view(views.events_on_date),
        name="events_on_date",
    ),
    path(
        "update/<int:id>/<str:year>/<str:month>/<str:day>/",
        calendar_view(views.update_event),
        name="update_event",
    ),
    path(
        "remove/<int:id>/<str:year>/<str:month>/<str:day>/",
        calendar_view(views.remove_event),
        name="remove_event",
    ),
    path(
        "remove-next/<int:id>/<str:year>/<str:month>/<str:day>/",
        calendar_view(views.remove_next),
        name="remove_next",
    ),
]
if settings.CALENDAR_PROFILE in ("private", "production"):
    urlpatterns += [
        path(
            "login/",
            auth_views.LoginView.as_view(template_name="registration/login.html"),
            name="login",
        ),
        path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    ]
