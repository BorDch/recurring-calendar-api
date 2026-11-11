"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from events import views

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth import views as auth_views
from django.views.decorators.csrf import csrf_exempt


def calendar_view(view, *, write=False):
    if settings.CALENDAR_PROFILE == 'private':
        return login_required(view)
    return csrf_exempt(view) if write else view


urlpatterns = [
    path('', calendar_view(views.calendar_home), name='calendar_home'),
    path('admin/', admin.site.urls),
    path('events/range/', calendar_view(views.events_range), name='events_range'),
    path('add/', calendar_view(views.add_event, write=True), name='add_event'),
    path('events/<str:year>/<str:month>/<str:day>/', calendar_view(views.events_on_date), name='events_on_date'),
    path('update/<int:id>/<str:year>/<str:month>/<str:day>/', calendar_view(views.update_event, write=True), name='update_event'),
    path('remove/<int:id>/<str:year>/<str:month>/<str:day>/', calendar_view(views.remove_event, write=True), name='remove_event'),
    path('remove-next/<int:id>/<str:year>/<str:month>/<str:day>/', calendar_view(views.remove_next, write=True), name='remove_next'),
]
if settings.CALENDAR_PROFILE == 'private':
    urlpatterns += [
        path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
        path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    ]
