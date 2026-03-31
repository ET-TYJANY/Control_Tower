from django.urls import path
from . import views

app_name = 'logistics'

urlpatterns = [
    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('dashboard/live/', views.live_dashboard_page, name='live_dashboard_page'),
    path('api/dashboard/live/', views.live_dashboard_api, name='live_dashboard_api'),

    # Missions
    path('missions/', views.MissionListView.as_view(), name='mission_list'),
    path('missions/<int:pk>/', views.MissionDetailView.as_view(), name='mission_detail'),
    path('missions/create/', views.MissionCreateView.as_view(), name='mission_create'),
    path('missions/<int:pk>/edit/', views.MissionUpdateView.as_view(), name='mission_update'),
    path('missions/<int:pk>/delete/', views.MissionDeleteView.as_view(), name='mission_delete'),

    # Trucks
    path('trucks/', views.TruckListView.as_view(), name='truck_list'),
    path('trucks/<int:pk>/', views.TruckDetailView.as_view(), name='truck_detail'),
    path('trucks/create/', views.TruckCreateView.as_view(), name='truck_create'),
    path('trucks/<int:pk>/edit/', views.TruckUpdateView.as_view(), name='truck_update'),
    path('trucks/<int:pk>/delete/', views.TruckDeleteView.as_view(), name='truck_delete'),

    # Stations
    path('stations/', views.StationListView.as_view(), name='station_list'),
    path('stations/<int:pk>/', views.StationDetailView.as_view(), name='station_detail'),
    path('stations/create/', views.StationCreateView.as_view(), name='station_create'),
    path('stations/<int:pk>/edit/', views.StationUpdateView.as_view(), name='station_update'),
    path('stations/<int:pk>/delete/', views.StationDeleteView.as_view(), name='station_delete'),

    # Depots
    path('depots/', views.DepotListView.as_view(), name='depot_list'),
    path('depots/<int:pk>/', views.DepotDetailView.as_view(), name='depot_detail'),
    path('depots/create/', views.DepotCreateView.as_view(), name='depot_create'),
    path('depots/<int:pk>/edit/', views.DepotUpdateView.as_view(), name='depot_update'),
    path('depots/<int:pk>/delete/', views.DepotDeleteView.as_view(), name='depot_delete'),
]