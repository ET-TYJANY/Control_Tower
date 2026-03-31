from django.contrib import admin
from .models import (
    Depot,
    Station,
    Driver,
    Truck,
    Mission,
    TruckCompartment,
    TruckTelemetry,
    RouteCheckpoint,
    FuelConsumptionLog,
    TruckAlert,
    Incident,
    DepotProductStock,
    StationTank,
    StationTLSSnapshot,
    DepotArrival,
    QualitySample,
    DepotStockComparison,
    MissionEvent,
)


@admin.register(Depot)
class DepotAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'capacity_total')
    search_fields = ('name', 'city')


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'region', 'risk_level', 'daily_consumption')
    search_fields = ('name', 'city', 'region')
    list_filter = ('risk_level', 'region')


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ('name', 'cin', 'phone', 'rating', 'active')
    search_fields = ('name', 'cin', 'phone')
    list_filter = ('active',)


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ('matricule', 'transporter', 'status', 'driver', 'fuel_level', 'capacity_total')
    search_fields = ('matricule', 'transporter', 'driver__name')
    list_filter = ('status', 'transporter')


@admin.register(Mission)
class MissionAdmin(admin.ModelAdmin):
    list_display = ('truck', 'depot', 'station', 'status', 'total_distance_km', 'eta_minutes')
    search_fields = ('truck__matricule', 'depot__name', 'station__name')
    list_filter = ('status',)


@admin.register(TruckCompartment)
class TruckCompartmentAdmin(admin.ModelAdmin):
    list_display = ('truck', 'mission', 'compartment_name', 'product', 'quantity', 'remaining_quantity', 'status')
    list_filter = ('product', 'status')
    search_fields = ('truck__matricule', 'compartment_name')


@admin.register(TruckTelemetry)
class TruckTelemetryAdmin(admin.ModelAdmin):
    list_display = ('truck', 'mission', 'latitude', 'longitude', 'speed', 'progress', 'status', 'recorded_at')
    list_filter = ('status', 'route_status')
    search_fields = ('truck__matricule',)


@admin.register(RouteCheckpoint)
class RouteCheckpointAdmin(admin.ModelAdmin):
    list_display = ('mission', 'sequence', 'name', 'expected_arrival_minutes', 'passed')
    list_filter = ('passed',)


@admin.register(FuelConsumptionLog)
class FuelConsumptionLogAdmin(admin.ModelAdmin):
    list_display = ('truck', 'mission', 'fuel_consumed', 'distance_traveled', 'consumption_rate', 'recorded_at')
    search_fields = ('truck__matricule',)


@admin.register(TruckAlert)
class TruckAlertAdmin(admin.ModelAdmin):
    list_display = ('truck', 'mission', 'alert_type', 'severity', 'resolved', 'created_at')
    list_filter = ('alert_type', 'severity', 'resolved')
    search_fields = ('truck__matricule', 'message')


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('type', 'severity', 'truck', 'mission', 'station', 'resolved', 'created_at')
    list_filter = ('type', 'severity', 'resolved')
    search_fields = ('truck__matricule', 'station__name')


@admin.register(DepotProductStock)
class DepotProductStockAdmin(admin.ModelAdmin):
    list_display = ('depot', 'product', 'current_volume', 'max_capacity', 'updated_at')
    list_filter = ('product',)
    search_fields = ('depot__name',)


@admin.register(StationTank)
class StationTankAdmin(admin.ModelAdmin):
    list_display = ('station', 'tank_name', 'product', 'max_capacity', 'current_volume', 'last_updated')
    list_filter = ('product',)
    search_fields = ('station__name', 'tank_name')


@admin.register(StationTLSSnapshot)
class StationTLSSnapshotAdmin(admin.ModelAdmin):
    list_display = ('station_tank', 'current_volume', 'temperature', 'water_level', 'sensor_status', 'updated_at')
    list_filter = ('sensor_status',)


@admin.register(DepotArrival)
class DepotArrivalAdmin(admin.ModelAdmin):
    list_display = ('depot', 'product', 'planned_volume', 'arrival_date', 'quality_status')
    list_filter = ('product', 'quality_status')
    search_fields = ('depot__name', 'supplier')


@admin.register(QualitySample)
class QualitySampleAdmin(admin.ModelAdmin):
    list_display = ('arrival', 'sample_code', 'density', 'temperature', 'water_content', 'result', 'analyzed_at')
    list_filter = ('result',)


@admin.register(DepotStockComparison)
class DepotStockComparisonAdmin(admin.ModelAdmin):
    list_display = ('depot', 'product', 'manual_volume', 'sensor_volume', 'variance', 'variance_percent', 'alert_level')
    list_filter = ('alert_level', 'product')
    search_fields = ('depot__name',)


@admin.register(MissionEvent)
class MissionEventAdmin(admin.ModelAdmin):
    list_display = ('mission', 'event_type', 'timestamp')
    list_filter = ('event_type',)
    search_fields = ('mission__truck__matricule', 'mission__station__name', 'description')