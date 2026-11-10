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

urlpatterns = [
    path('', views.calendar_home, name='calendar_home'),
    path('admin/', admin.site.urls),
    path('events/range/', views.events_range, name='events_range'),
    path('add/', views.add_event, name='add_event'),
    path('events/<str:year>/<str:month>/<str:day>/', views.events_on_date, name='events_on_date'),
    path('update/<int:id>/<str:year>/<str:month>/<str:day>/', views.update_event, name='update_event'),
    path('remove/<int:id>/<str:year>/<str:month>/<str:day>/', views.remove_event, name='remove_event'),
    path('remove-next/<int:id>/<str:year>/<str:month>/<str:day>/', views.remove_next, name='remove_next'),
]
