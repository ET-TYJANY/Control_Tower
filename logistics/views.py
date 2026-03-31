from django.shortcuts import render
from rest_framework import viewsets
from .models import Depot, Station, Driver, Truck, Mission, Incident
from .serializers import (
    DepotSerializer,
    StationSerializer,
    DriverSerializer,
    TruckSerializer,
    MissionSerializer,
    IncidentSerializer
)


class DepotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Depot.objects.all()
    serializer_class = DepotSerializer


class StationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Station.objects.all()
    serializer_class = StationSerializer


class DriverViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer


class TruckViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Truck.objects.all()
    serializer_class = TruckSerializer


class MissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Mission.objects.all()
    serializer_class = MissionSerializer


class IncidentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Incident.objects.all()
    serializer_class = IncidentSerializer



from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Mission, Incident


@api_view(['GET'])
def transport_dashboard(request):
    missions = Mission.objects.select_related(
        'truck',
        'truck__driver',
        'depot',
        'station'
    ).all()

    data = []

    for mission in missions:
        truck = mission.truck
        driver = truck.driver

        latest_incident = Incident.objects.filter(truck=truck).order_by('-created_at').first()

        data.append({
            "truck_id": truck.id,
            "matricule": truck.matricule,
            "transporter": truck.transporter,
            "status": truck.status,
            "current_position": {
                "lat": truck.current_lat,
                "lng": truck.current_lng
            },
            "driver": {
                "name": driver.name,
                "cin": driver.cin,
                "phone": driver.phone,
                "rating": driver.rating
            },
            "mission": {
                "id": mission.id,
                "product": mission.product,
                "quantity": mission.quantity,
                "departure_time": mission.departure_time,
                "eta": mission.eta,
                "delivered_quantity": mission.delivered_quantity,
                "status": mission.status
            },
            "depot": {
                "id": mission.depot.id,
                "name": mission.depot.name,
                "city": mission.depot.city
            },
            "station": {
                "id": mission.station.id,
                "name": mission.station.name,
                "city": mission.station.city,
                "region": mission.station.region,
                "risk_level": mission.station.risk_level
            },
            "incident": None if not latest_incident else {
                "id": latest_incident.id,
                "type": latest_incident.type,
                "severity": latest_incident.severity,
                "description": latest_incident.description,
                "created_at": latest_incident.created_at
            }
        })

    return Response(data)


from logistics.models import DepotProductStock, StationTLSSnapshot, TruckTelemetry
from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def live_dashboard(request):
    depot_stocks = DepotProductStock.objects.select_related('depot').all()
    station_snapshots = StationTLSSnapshot.objects.select_related(
        'station_tank',
        'station_tank__station'
    ).all()
    truck_telemetries = TruckTelemetry.objects.select_related(
        'truck',
        'mission',
        'mission__depot',
        'mission__station'
    ).all()

    depot_data = [
        {
            "depot": stock.depot.name,
            "city": stock.depot.city,
            "product": stock.product,
            "current_volume": stock.current_volume,
            "max_capacity": stock.max_capacity,
            "updated_at": stock.updated_at,
        }
        for stock in depot_stocks
    ]

    station_data = [
        {
            "station": snap.station_tank.station.name,
            "city": snap.station_tank.station.city,
            "tank_name": snap.station_tank.tank_name,
            "product": snap.station_tank.product,
            "current_volume": snap.current_volume,
            "temperature": snap.temperature,
            "water_level": snap.water_level,
            "sensor_status": snap.sensor_status,
            "updated_at": snap.updated_at,
        }
        for snap in station_snapshots
    ]

    truck_data = [
        {
            "truck": telemetry.truck.matricule,
            "status": telemetry.status,
            "latitude": telemetry.latitude,
            "longitude": telemetry.longitude,
            "speed": telemetry.speed,
            "heading": telemetry.heading,
            "progress": telemetry.progress,
            "mission": None if not telemetry.mission else {
                "product": telemetry.mission.product,
                "quantity": telemetry.mission.quantity,
                "status": telemetry.mission.status,
                "depot": telemetry.mission.depot.name,
                "station": telemetry.mission.station.name,
            },
            "updated_at": telemetry.updated_at,
        }
        for telemetry in truck_telemetries
    ]

    return Response({
        "depots": depot_data,
        "stations": station_data,
        "trucks": truck_data,
    })



def live_dashboard_page(request):
    return render(request, 'logistics/live_dashboard.html')






from django.http import JsonResponse
from django.views import View
from django.db.models import Prefetch, OuterRef, Subquery
from .models import (
    Truck, TruckTelemetry, Mission, DepotProductStock,
    StationTank, StationTLSSnapshot, TruckCompartment
)
from django.utils import timezone

class LiveDashboardDataView(View):
    """
    API endpoint returning live data for the control tower dashboard:
    - trucks with latest telemetry and mission info
    - depot product stocks
    - station tanks with latest TLS snapshot
    """
    def get(self, request):
        # ----- Trucks -----
        # Subquery to get latest telemetry per truck
        latest_telemetry = TruckTelemetry.objects.filter(
            truck=OuterRef('pk')
        ).order_by('-recorded_at')

        trucks_qs = Truck.objects.filter(
            status__in=['ON_ROUTE', 'STOPPED', 'DELAYED']
        ).annotate(
            last_lat=Subquery(latest_telemetry.values('latitude')[:1]),
            last_lng=Subquery(latest_telemetry.values('longitude')[:1]),
            last_speed=Subquery(latest_telemetry.values('speed')[:1]),
            last_progress=Subquery(latest_telemetry.values('progress')[:1]),
            last_status=Subquery(latest_telemetry.values('status')[:1]),
        ).prefetch_related(
            Prefetch('missions', queryset=Mission.objects.filter(
                status__in=['IN_TRANSIT', 'ARRIVED', 'UNLOADING']
            ).select_related('depot', 'station'), to_attr='active_missions')
        )

        trucks_data = []
        for truck in trucks_qs:
            # Get current mission (if any)
            mission = truck.active_missions[0] if truck.active_missions else None

            # Determine status for frontend (map from telemetry status)
            frontend_status = truck.last_status or 'IDLE'
            if frontend_status == 'IN_TRANSIT':
                frontend_status = 'IN_TRANSIT'
            elif frontend_status == 'STOPPED':
                frontend_status = 'STOPPED'
            elif frontend_status == 'ALERT':
                frontend_status = 'ALERT'
            else:
                frontend_status = 'IDLE'

            # Get product and quantity from compartments for this mission
            product = None
            quantity = None
            if mission:
                compartments = TruckCompartment.objects.filter(
                    truck=truck, mission=mission
                ).first()
                if compartments:
                    product = compartments.product
                    quantity = compartments.quantity

            trucks_data.append({
                'truck': truck.matricule,
                'status': frontend_status,
                'latitude': truck.last_lat,
                'longitude': truck.last_lng,
                'speed': truck.last_speed or 0,
                'progress': truck.last_progress or 0,
                'mission': {
                    'depot': mission.depot.name if mission else None,
                    'station': mission.station.name if mission else None,
                    'product': product,
                    'quantity': quantity,
                } if mission else None,
            })

        # ----- Depots -----
        depot_stocks = DepotProductStock.objects.select_related('depot')
        depots_data = []
        for stock in depot_stocks:
            depots_data.append({
                'depot': stock.depot.name,
                'city': stock.depot.city,
                'product': stock.product,
                'current_volume': stock.current_volume,
                'max_capacity': stock.max_capacity,
            })

        # ----- Stations -----
        # Get latest TLS snapshot for each tank
        latest_snapshot = StationTLSSnapshot.objects.filter(
            station_tank=OuterRef('pk')
        ).order_by('-updated_at')

        tanks_qs = StationTank.objects.select_related('station').annotate(
            last_volume=Subquery(latest_snapshot.values('current_volume')[:1]),
            last_temp=Subquery(latest_snapshot.values('temperature')[:1]),
            last_water=Subquery(latest_snapshot.values('water_level')[:1]),
            last_sensor=Subquery(latest_snapshot.values('sensor_status')[:1]),
        )

        stations_data = []
        for tank in tanks_qs:
            stations_data.append({
                'station': tank.station.name,
                'city': tank.station.city,
                'tank_name': tank.tank_name,
                'product': tank.product,
                'current_volume': tank.last_volume or 0,
                'temperature': tank.last_temp or 0,
                'water_level': tank.last_water or 0,
                'sensor_status': tank.last_sensor or 'OK',
            })

        return JsonResponse({
            'trucks': trucks_data,
            'depots': depots_data,
            'stations': stations_data,
        })

from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Count, Q
from .models import Mission, Truck, Station, TruckAlert, TruckTelemetry, Depot
from .forms import MissionForm, TruckForm, StationForm, DepotForm

# ---------- Dashboard ----------
def dashboard(request):
    from django.shortcuts import render
    from django.db.models import Count

    context = {
        'total_missions': Mission.objects.count(),
        'total_trucks': Truck.objects.count(),
        'total_stations': Station.objects.count(),
        'missions_planned': Mission.objects.filter(status='PLANNED').count(),
        'missions_in_transit': Mission.objects.filter(status='IN_TRANSIT').count(),
        'missions_completed': Mission.objects.filter(status='COMPLETED').count(),
        'missions_cancelled': Mission.objects.filter(status='CANCELLED').count(),
        'recent_missions': Mission.objects.order_by('-created_at')[:5],
        'low_fuel_alerts': TruckAlert.objects.filter(alert_type='LOW_FUEL', resolved=False).count(),
        'active_trucks': Truck.objects.filter(status__in=['ON_ROUTE', 'STOPPED', 'DELAYED']).count(),
    }
    return render(request, 'logistics/dashboard.html', context)
from django.shortcuts import render

# ---------- Mission ----------
class MissionListView(ListView):
    model = Mission
    template_name = 'logistics/mission_list.html'
    context_object_name = 'missions'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(truck__matricule__icontains=search) |
                Q(depot__name__icontains=search) |
                Q(station__name__icontains=search)
            )
        return qs.select_related('truck', 'depot', 'station')

class MissionDetailView(DetailView):
    model = Mission
    template_name = 'logistics/mission_detail.html'
    context_object_name = 'mission'

class MissionCreateView(SuccessMessageMixin, CreateView):
    model = Mission
    form_class = MissionForm
    template_name = 'logistics/mission_form.html'
    success_url = reverse_lazy('mission_list')
    success_message = "Mission créée avec succès."

class MissionUpdateView(SuccessMessageMixin, UpdateView):
    model = Mission
    form_class = MissionForm
    template_name = 'logistics/mission_form.html'
    success_url = reverse_lazy('mission_list')
    success_message = "Mission mise à jour."

class MissionDeleteView(DeleteView):
    model = Mission
    template_name = 'logistics/mission_confirm_delete.html'
    success_url = reverse_lazy('mission_list')

# ---------- Truck ----------
class TruckListView(ListView):
    model = Truck
    template_name = 'logistics/truck_list.html'
    context_object_name = 'trucks'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(matricule__icontains=search) |
                Q(transporter__icontains=search) |
                Q(driver__name__icontains=search)
            )
        return qs.select_related('driver')

class TruckDetailView(DetailView):
    model = Truck
    template_name = 'logistics/truck_detail.html'
    context_object_name = 'truck'

class TruckCreateView(SuccessMessageMixin, CreateView):
    model = Truck
    form_class = TruckForm
    template_name = 'logistics/truck_form.html'
    success_url = reverse_lazy('truck_list')
    success_message = "Camion ajouté."

class TruckUpdateView(SuccessMessageMixin, UpdateView):
    model = Truck
    form_class = TruckForm
    template_name = 'logistics/truck_form.html'
    success_url = reverse_lazy('truck_list')
    success_message = "Camion modifié."

class TruckDeleteView(DeleteView):
    model = Truck
    template_name = 'logistics/truck_confirm_delete.html'
    success_url = reverse_lazy('truck_list')

# ---------- Station ----------
class StationListView(ListView):
    model = Station
    template_name = 'logistics/station_list.html'
    context_object_name = 'stations'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(city__icontains=search) |
                Q(region__icontains=search)
            )
        return qs.prefetch_related('tanks')

class StationDetailView(DetailView):
    model = Station
    template_name = 'logistics/station_detail.html'
    context_object_name = 'station'

class StationCreateView(SuccessMessageMixin, CreateView):
    model = Station
    form_class = StationForm
    template_name = 'logistics/station_form.html'
    success_url = reverse_lazy('station_list')
    success_message = "Station ajoutée."

class StationUpdateView(SuccessMessageMixin, UpdateView):
    model = Station
    form_class = StationForm
    template_name = 'logistics/station_form.html'
    success_url = reverse_lazy('station_list')
    success_message = "Station modifiée."

class StationDeleteView(DeleteView):
    model = Station
    template_name = 'logistics/station_confirm_delete.html'
    success_url = reverse_lazy('station_list')


def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['title'] = 'Nouveau camion' if not self.object else f'Modifier {self.object}'
    context['cancel_url'] = reverse_lazy('logistics:truck_list')
    return context


def get_context_data(self, **kwargs):
    context = super().get_context_data(**kwargs)
    context['list_url'] = 'logistics:station_list'  # à adapter
    return context


# logistics/views.py

# ----- Depot -----
class DepotListView(ListView):
    model = Depot
    template_name = 'logistics/depot_list.html'
    context_object_name = 'depots'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.GET.get('search')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(city__icontains=search)
            )
        return qs.prefetch_related('product_stocks')

class DepotDetailView(DetailView):
    model = Depot
    template_name = 'logistics/depot_detail.html'
    context_object_name = 'depot'

class DepotCreateView(SuccessMessageMixin, CreateView):
    model = Depot
    form_class = DepotForm
    template_name = 'logistics/depot_form.html'
    success_url = reverse_lazy('logistics:depot_list')
    success_message = "Dépôt créé avec succès."

class DepotUpdateView(SuccessMessageMixin, UpdateView):
    model = Depot
    form_class = DepotForm
    template_name = 'logistics/depot_form.html'
    success_url = reverse_lazy('logistics:depot_list')
    success_message = "Dépôt mis à jour."

class DepotDeleteView(DeleteView):
    model = Depot
    template_name = 'logistics/depot_confirm_delete.html'
    success_url = reverse_lazy('logistics:depot_list')


def live_dashboard_page(request):
    return render(request, 'logistics/live_dashboard.html')

from django.http import JsonResponse
from django.db.models import OuterRef, Subquery
from .models import Truck, TruckTelemetry, Mission, DepotProductStock, StationTank, StationTLSSnapshot, TruckCompartment

def live_dashboard_api(request):
    """API endpoint renvoyant les données temps réel pour le dashboard."""
    # ----- Trucks -----
    latest_telemetry = TruckTelemetry.objects.filter(
        truck=OuterRef('pk')
    ).order_by('-recorded_at')

    trucks = Truck.objects.filter(
        status__in=['ON_ROUTE', 'STOPPED', 'DELAYED']
    ).annotate(
        last_lat=Subquery(latest_telemetry.values('latitude')[:1]),
        last_lng=Subquery(latest_telemetry.values('longitude')[:1]),
        last_speed=Subquery(latest_telemetry.values('speed')[:1]),
        last_progress=Subquery(latest_telemetry.values('progress')[:1]),
        last_status=Subquery(latest_telemetry.values('status')[:1]),
    ).select_related('driver')

    trucks_data = []
    for truck in trucks:
        mission = truck.missions.filter(
            status__in=['IN_TRANSIT', 'ARRIVED', 'UNLOADING']
        ).select_related('depot', 'station').first()

        telemetry_status = truck.last_status or 'IDLE'
        if telemetry_status == 'IN_TRANSIT':
            frontend_status = 'IN_TRANSIT'
        elif telemetry_status == 'STOPPED':
            frontend_status = 'STOPPED'
        elif telemetry_status == 'ALERT':
            frontend_status = 'ALERT'
        else:
            frontend_status = 'IDLE'

        product = None
        quantity = None
        if mission:
            compartments = TruckCompartment.objects.filter(
                truck=truck, mission=mission
            ).first()
            if compartments:
                product = compartments.product
                quantity = compartments.quantity

        trucks_data.append({
            'truck': truck.matricule,
            'status': frontend_status,
            'latitude': truck.last_lat,
            'longitude': truck.last_lng,
            'speed': truck.last_speed or 0,
            'progress': truck.last_progress or 0,
            'mission': {
                'depot': mission.depot.name if mission else None,
                'station': mission.station.name if mission else None,
                'product': product,
                'quantity': quantity,
            } if mission else None,
        })

    # ----- Depots -----
    depot_stocks = DepotProductStock.objects.select_related('depot')
    depots_data = [
        {
            'depot': stock.depot.name,
            'city': stock.depot.city,
            'product': stock.product,
            'current_volume': stock.current_volume,
            'max_capacity': stock.max_capacity,
        }
        for stock in depot_stocks
    ]

    # ----- Stations -----
    latest_snapshot = StationTLSSnapshot.objects.filter(
        station_tank=OuterRef('pk')
    ).order_by('-updated_at')

    station_tanks = StationTank.objects.select_related('station').annotate(
        last_volume=Subquery(latest_snapshot.values('current_volume')[:1]),
        last_temp=Subquery(latest_snapshot.values('temperature')[:1]),
        last_water=Subquery(latest_snapshot.values('water_level')[:1]),
        last_sensor=Subquery(latest_snapshot.values('sensor_status')[:1]),
    )

    stations_data = [
        {
            'station': tank.station.name,
            'city': tank.station.city,
            'tank_name': tank.tank_name,
            'product': tank.product,
            'current_volume': tank.last_volume or 0,
            'temperature': tank.last_temp or 0,
            'water_level': tank.last_water or 0,
            'sensor_status': tank.last_sensor or 'OK',
        }
        for tank in station_tanks
    ]

    return JsonResponse({
        'trucks': trucks_data,
        'depots': depots_data,
        'stations': stations_data,
    })




from .models import Mission, Truck, Station, Depot, TruckAlert

def dashboard(request):
    recent_missions = Mission.objects.select_related('truck', 'depot', 'station').order_by('-departure_time')[:5]
    depots = Depot.objects.all().order_by('name')[:10]

    context = {
        'total_missions': Mission.objects.count(),
        'active_trucks': Truck.objects.filter(status='ON_ROUTE').count(),
        'total_stations': Station.objects.count(),
        'total_depots': Depot.objects.count(),

        'low_fuel_alerts': TruckAlert.objects.filter(alert_type='LOW_FUEL', resolved=False).count(),
        'delay_alerts': TruckAlert.objects.filter(alert_type='DELAY', resolved=False).count(),
        'deviation_alerts': TruckAlert.objects.filter(alert_type__in=['DEVIATION', 'OFF_ROUTE'], resolved=False).count(),
        'critical_alerts': TruckAlert.objects.filter(severity='CRITICAL', resolved=False).count(),

        'missions_planned': Mission.objects.filter(status='PLANNED').count(),
        'missions_in_transit': Mission.objects.filter(status='IN_TRANSIT').count(),
        'missions_completed': Mission.objects.filter(status='COMPLETED').count(),
        'missions_cancelled': Mission.objects.filter(status='CANCELLED').count(),

        'recent_missions': recent_missions,
        'depots': depots,
    }
    return render(request, 'logistics/dashboard.html', context)