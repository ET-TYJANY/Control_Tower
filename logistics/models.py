from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


# ========================
# DEPOT
# ========================
class Depot(models.Model):
    """Dépôt de stockage de produits pétroliers"""
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    capacity_total = models.FloatField(help_text="Capacité totale du dépôt en litres")
    address = models.TextField(blank=True, default='')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} - {self.city}"

    def get_available_capacity(self):
        total_used = sum(stock.current_volume for stock in self.product_stocks.all())
        return self.capacity_total - total_used

    def get_used_capacity(self):
        return sum(stock.current_volume for stock in self.product_stocks.all())

    def get_fill_percentage(self):
        if self.capacity_total > 0:
            return (self.get_used_capacity() / self.capacity_total) * 100
        return 0


# ========================
# STATION
# ========================
class Station(models.Model):
    """Station-service avec cuves de stockage"""
    name = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    region = models.CharField(max_length=100)
    address = models.TextField(blank=True, default='')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    stock = models.JSONField(default=dict, blank=True)
    daily_consumption = models.FloatField(default=0)

    RISK_LEVEL_CHOICES = [
        ('NORMAL', 'Normal'),
        ('WARNING', 'Warning'),
        ('CRITICAL', 'Critical'),
    ]
    risk_level = models.CharField(max_length=10, choices=RISK_LEVEL_CHOICES, default='NORMAL')

    def __str__(self):
        return self.name

    def update_risk_level(self):
        for tank in self.tanks.all():
            if tank.current_volume < 8000:
                self.risk_level = 'CRITICAL'
                self.save(update_fields=['risk_level'])
                return
            elif tank.current_volume < 15000:
                self.risk_level = 'WARNING'
                self.save(update_fields=['risk_level'])
                return
        self.risk_level = 'NORMAL'
        self.save(update_fields=['risk_level'])


# ========================
# DRIVER
# ========================
class Driver(models.Model):
    """Chauffeur de camion"""
    name = models.CharField(max_length=100)
    cin = models.CharField(max_length=50, unique=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True, default='')
    rating = models.FloatField(default=4.0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    total_trips = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    hire_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.name


# ========================
# TRUCK
# ========================
class Truck(models.Model):
    """Camion de transport avec gestion de carburant et capacités"""
    matricule = models.CharField(max_length=50, unique=True)
    transporter = models.CharField(max_length=100)
    brand = models.CharField(max_length=50, blank=True, default='')
    model = models.CharField(max_length=50, blank=True, default='')
    year = models.IntegerField(null=True, blank=True)

    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='trucks')

    capacity_total = models.FloatField(help_text="Capacité totale de chargement en litres")
    max_compartment_count = models.IntegerField(default=3, help_text="Nombre maximum de compartiments")

    fuel_tank_capacity = models.FloatField(help_text="Capacité du réservoir de carburant en litres")
    fuel_level = models.FloatField(default=100, help_text="Niveau de carburant actuel en litres")
    fuel_consumption_per_km = models.FloatField(default=0.35, help_text="Consommation moyenne en L/km")
    fuel_consumption_idle = models.FloatField(default=0.5, help_text="Consommation au ralenti en L/h")

    total_odometer = models.FloatField(default=0, help_text="Kilométrage total en km")
    trip_odometer = models.FloatField(default=0, help_text="Kilométrage du trajet actuel en km")
    last_maintenance_km = models.FloatField(default=0)
    next_maintenance_km = models.FloatField(default=0)

    STATUS_CHOICES = [
        ('AVAILABLE', 'Disponible'),
        ('ON_ROUTE', 'En route'),
        ('STOPPED', 'À l’arrêt'),
        ('DELAYED', 'En retard'),
        ('UNLOADING', 'Déchargement'),
        ('COMPLETED', 'Terminé'),
        ('BREAKDOWN', 'Panne'),
        ('MAINTENANCE', 'En maintenance'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE')

    current_lat = models.FloatField(default=0)
    current_lng = models.FloatField(default=0)

    last_fuel_refill = models.DateTimeField(null=True, blank=True)
    last_maintenance = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.matricule} - {self.transporter}"

    def get_remaining_fuel_range(self):
        if self.fuel_consumption_per_km > 0:
            return self.fuel_level / self.fuel_consumption_per_km
        return 0

    def get_fuel_percentage(self):
        if self.fuel_tank_capacity > 0:
            return (self.fuel_level / self.fuel_tank_capacity) * 100
        return 0

    def get_total_load(self):
        return sum(
            comp.quantity for comp in self.compartments.filter(
                mission__status__in=['LOADING', 'IN_TRANSIT']
            )
        )

    def get_current_mission(self):
        return self.missions.filter(
            status__in=['PLANNED', 'LOADING', 'IN_TRANSIT', 'ARRIVED', 'UNLOADING']
        ).first()

    def get_latest_telemetry(self):
        return self.telemetries.first()

    def get_current_speed(self):
        latest = self.get_latest_telemetry()
        return latest.speed if latest else 0

    def get_eta_minutes(self):
        latest = self.get_latest_telemetry()
        if latest and latest.eta_minutes is not None:
            return latest.eta_minutes
        return 0

    def is_operational(self):
        return self.status not in ['BREAKDOWN', 'MAINTENANCE'] and self.get_fuel_percentage() > 10

    def get_status_summary(self):
        latest_telemetry = self.get_latest_telemetry()
        current_mission = self.get_current_mission()
        fuel_alert = self.get_fuel_percentage() < 15

        return {
            'matricule': self.matricule,
            'status': self.status,
            'is_operational': self.is_operational(),
            'fuel_level': self.fuel_level,
            'fuel_percentage': self.get_fuel_percentage(),
            'fuel_alert': fuel_alert,
            'remaining_range_km': self.get_remaining_fuel_range(),
            'total_load': self.get_total_load(),
            'capacity_used_percentage': (self.get_total_load() / self.capacity_total * 100) if self.capacity_total > 0 else 0,
            'current_speed': self.get_current_speed(),
            'eta_minutes': self.get_eta_minutes(),
            'alerts_count': self.alerts.filter(resolved=False).count(),
            'current_location': {
                'lat': self.current_lat,
                'lng': self.current_lng,
            },
            'route_status': latest_telemetry.route_status if latest_telemetry else 'UNKNOWN',
            'deviation_km': latest_telemetry.deviation_km if latest_telemetry else 0,
            'delay_status': current_mission.eta < timezone.now() if current_mission and current_mission.eta else False,
            'current_mission': {
                'id': current_mission.id if current_mission else None,
                'depot': current_mission.depot.name if current_mission else None,
                'station': current_mission.station.name if current_mission else None,
                'progress': current_mission.get_progress_percentage() if current_mission else 0,
                'remaining_distance': current_mission.remaining_distance_km if current_mission else 0,
            } if current_mission else None
        }

    def update_fuel_level(self, consumed_liters):
        self.fuel_level = max(0, self.fuel_level - consumed_liters)
        self.save(update_fields=['fuel_level', 'updated_at'])

    def validate_load(self):
        total_load = self.get_total_load()
        if total_load > self.capacity_total:
            raise ValueError(
                f"Charge totale ({total_load} L) dépasse la capacité du camion ({self.capacity_total} L)"
            )
        return True


# ========================
# MISSION
# ========================
class Mission(models.Model):
    """Mission de transport d'un camion"""
    truck = models.ForeignKey(Truck, on_delete=models.CASCADE, related_name='missions')
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE)
    station = models.ForeignKey(Station, on_delete=models.CASCADE)

    route_polyline = models.TextField(blank=True, default='', help_text="Encoded polyline du trajet prévu")
    total_distance_km = models.FloatField(default=0, help_text="Distance totale en km")
    estimated_duration_minutes = models.IntegerField(default=0, help_text="Durée estimée en minutes")

    remaining_distance_km = models.FloatField(default=0)
    eta_minutes = models.IntegerField(null=True, blank=True)
    deviation_km = models.FloatField(default=0, help_text="Distance de déviation en km")
    traveled_distance_km = models.FloatField(default=0, help_text="Distance déjà parcourue")

    departure_time = models.DateTimeField(default=timezone.now)
    actual_departure_time = models.DateTimeField(null=True, blank=True)
    eta = models.DateTimeField(null=True, blank=True)
    actual_arrival_time = models.DateTimeField(null=True, blank=True)

    delivered_quantity = models.FloatField(null=True, blank=True)

    STATUS_CHOICES = [
        ('PLANNED', 'Planifiée'),
        ('LOADING', 'Chargement'),
        ('IN_TRANSIT', 'En transit'),
        ('ARRIVED', 'Arrivé'),
        ('UNLOADING', 'Déchargement'),
        ('COMPLETED', 'Terminé'),
        ('CANCELLED', 'Annulée'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PLANNED')

    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.truck.matricule} → {self.station.name}"

    def get_latest_telemetry(self):
        return self.telemetries.first()

    def calculate_eta_from_remaining(self):
        latest_telemetry = self.get_latest_telemetry()
        if not latest_telemetry:
            return self.eta_minutes

        speed = latest_telemetry.speed
        if speed <= 0:
            return self.eta_minutes

        if self.remaining_distance_km > 0:
            eta_minutes_calculated = int((self.remaining_distance_km / speed) * 60)
            self.eta_minutes = eta_minutes_calculated
            self.eta = timezone.now() + timedelta(minutes=eta_minutes_calculated)
            self.save(update_fields=['eta_minutes', 'eta', 'updated_at'])

            if self.eta and self.eta < timezone.now() and self.status not in ['COMPLETED', 'CANCELLED']:
                last_alert = self.truck.alerts.filter(
                    mission=self,
                    alert_type='DELAY',
                    resolved=False,
                    created_at__gte=timezone.now() - timedelta(minutes=15)
                ).first()

                if not last_alert:
                    TruckAlert.objects.create(
                        truck=self.truck,
                        mission=self,
                        alert_type='DELAY',
                        severity='CRITICAL',
                        message=f"Retard sur la mission {self.id}",
                        value=(timezone.now() - self.eta).total_seconds() / 60,
                        threshold=0
                    )

        return self.eta_minutes

    def get_progress_percentage(self):
        if self.total_distance_km > 0:
            traveled = self.total_distance_km - self.remaining_distance_km
            progress = (traveled / self.total_distance_km) * 100
            return max(0, min(100, progress))
        return 0

    def update_remaining_distance(self, new_remaining):
        self.remaining_distance_km = new_remaining
        self.save(update_fields=['remaining_distance_km', 'updated_at'])
        self.calculate_eta_from_remaining()


# ========================
# TRUCK COMPARTMENT
# ========================
class TruckCompartment(models.Model):
    """Compartiment de camion pour le transport de produits"""
    PRODUCT_CHOICES = [
        ('JET', 'JET'),
        ('SSP', 'SSP'),
        ('GAZOIL', 'Gazoil'),
        ('FUEL', 'Fuel'),
    ]

    truck = models.ForeignKey(Truck, on_delete=models.CASCADE, related_name='compartments')
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='compartments', null=True, blank=True)
    compartment_name = models.CharField(max_length=50)
    product = models.CharField(max_length=20, choices=PRODUCT_CHOICES)
    quantity = models.FloatField(validators=[MinValueValidator(0)])
    max_capacity = models.FloatField(validators=[MinValueValidator(0)])
    remaining_quantity = models.FloatField(validators=[MinValueValidator(0)], help_text="Quantité restante après livraisons partielles")

    status = models.CharField(max_length=20, default='LOADED', choices=[
        ('LOADED', 'Chargé'),
        ('PARTIAL', 'Partiellement déchargé'),
        ('EMPTY', 'Vide'),
    ])

    def __str__(self):
        return f"{self.truck.matricule} - {self.compartment_name} - {self.product}"

    def save(self, *args, **kwargs):
        if self.quantity > self.max_capacity:
            raise ValueError(
                f"Quantité ({self.quantity} L) dépasse la capacité maximale ({self.max_capacity} L)"
            )

        if self.remaining_quantity > self.quantity:
            raise ValueError(
                f"Quantité restante ({self.remaining_quantity} L) ne peut pas dépasser la quantité initiale ({self.quantity} L)"
            )

        other_compartments_sum = sum(
            comp.quantity for comp in self.truck.compartments.exclude(id=self.id)
        )
        total_load = other_compartments_sum + self.quantity

        if total_load > self.truck.capacity_total:
            raise ValueError(
                f"Charge totale ({total_load} L) dépasse la capacité du camion ({self.truck.capacity_total} L)"
            )

        super().save(*args, **kwargs)

    def get_fill_percentage(self):
        if self.max_capacity > 0:
            return (self.quantity / self.max_capacity) * 100
        return 0

    def get_remaining_percentage(self):
        if self.quantity > 0:
            return (self.remaining_quantity / self.quantity) * 100
        return 0

    def update_after_delivery(self, delivered_quantity):
        self.remaining_quantity = max(0, self.remaining_quantity - delivered_quantity)
        if self.remaining_quantity == 0:
            self.status = 'EMPTY'
        elif self.remaining_quantity < self.quantity:
            self.status = 'PARTIAL'
        self.save(update_fields=['remaining_quantity', 'status'])


# ========================
# TRUCK TELEMETRY
# ========================
class TruckTelemetry(models.Model):
    """Télémetrie temps réel du camion"""
    TELEMETRY_STATUS_CHOICES = [
        ('IDLE', 'Idle'),
        ('IN_TRANSIT', 'In Transit'),
        ('STOPPED', 'Stopped'),
        ('ARRIVED', 'Arrived'),
        ('UNLOADING', 'Unloading'),
        ('COMPLETED', 'Completed'),
        ('ALERT', 'Alert'),
    ]

    ROUTE_STATUS_CHOICES = [
        ('ON_TRACK', 'On Track'),
        ('DEVIATION', 'Deviation'),
        ('OFF_ROUTE', 'Off Route'),
        ('UNKNOWN', 'Unknown'),
    ]

    truck = models.ForeignKey(Truck, on_delete=models.CASCADE, related_name='telemetries')
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='telemetries', null=True, blank=True)

    latitude = models.FloatField()
    longitude = models.FloatField()
    altitude = models.FloatField(null=True, blank=True)

    speed = models.FloatField(default=0, validators=[MinValueValidator(0)])
    heading = models.FloatField(default=0)
    acceleration = models.FloatField(default=0)
    braking = models.FloatField(default=0)

    progress = models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    remaining_distance_km = models.FloatField(default=0)
    eta_minutes = models.IntegerField(null=True, blank=True)
    route_status = models.CharField(max_length=20, choices=ROUTE_STATUS_CHOICES, default='UNKNOWN')
    deviation_km = models.FloatField(default=0)

    fuel_consumed_since_start = models.FloatField(default=0)
    instant_fuel_consumption = models.FloatField(default=0)
    average_fuel_consumption = models.FloatField(default=0)

    status = models.CharField(max_length=20, choices=TELEMETRY_STATUS_CHOICES, default='IDLE')
    engine_status = models.BooleanField(default=True)
    gps_signal = models.IntegerField(default=100, validators=[MinValueValidator(0), MaxValueValidator(100)])

    recorded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-recorded_at']
        get_latest_by = 'recorded_at'

    def __str__(self):
        return f"{self.truck.matricule} - {self.status} - {self.recorded_at}"

    def save(self, *args, **kwargs):
        if self.deviation_km < 1:
            self.route_status = 'ON_TRACK'
        elif 1 <= self.deviation_km <= 5:
            self.route_status = 'DEVIATION'
        elif self.deviation_km > 5:
            self.route_status = 'OFF_ROUTE'

        if self.mission and self.mission.total_distance_km > 0:
            traveled = self.mission.total_distance_km - self.remaining_distance_km
            self.progress = min(100, max(0, (traveled / self.mission.total_distance_km) * 100))

        if self.speed > 0 and self.remaining_distance_km > 0:
            self.eta_minutes = int((self.remaining_distance_km / self.speed) * 60)
        elif self.speed == 0:
            self.eta_minutes = None

        super().save(*args, **kwargs)

        # Important:
        # le fuel est déjà géré par le script de simulation.
        # Ici on évite toute double consommation.

        self.check_alerts()

    def check_alerts(self):
        def create_or_refresh_alert(alert_type, severity, message, value, threshold, cooldown_minutes, use_mission=True):
            filters = {
                'truck': self.truck,
                'alert_type': alert_type,
                'resolved': False,
            }
            if use_mission:
                filters['mission'] = self.mission

            existing_alert = TruckAlert.objects.filter(**filters).first()

            if existing_alert:
                if existing_alert.created_at >= timezone.now() - timedelta(minutes=cooldown_minutes):
                    return existing_alert

                existing_alert.severity = severity
                existing_alert.message = message
                existing_alert.value = value
                existing_alert.threshold = threshold
                existing_alert.mission = self.mission
                existing_alert.save(update_fields=[
                    'severity', 'message', 'value', 'threshold', 'mission'
                ])
                return existing_alert

            create_data = {
                'truck': self.truck,
                'alert_type': alert_type,
                'severity': severity,
                'message': message,
                'value': value,
                'threshold': threshold,
            }
            if use_mission:
                create_data['mission'] = self.mission

            return TruckAlert.objects.create(**create_data)

        if self.deviation_km > 5:
            create_or_refresh_alert(
                alert_type='DEVIATION',
                severity='CRITICAL',
                message=f"Déviation importante: {self.deviation_km:.1f} km hors itinéraire",
                value=self.deviation_km,
                threshold=5,
                cooldown_minutes=30,
                use_mission=True
            )

        recent_telemetries = self.truck.telemetries.filter(
            recorded_at__gte=timezone.now() - timedelta(hours=2)
        ).order_by('recorded_at')

        if len(recent_telemetries) > 1:
            stop_start = None
            longest_stop = 0
            current_stop = 0

            for telemetry in recent_telemetries:
                if telemetry.speed == 0:
                    if stop_start is None:
                        stop_start = telemetry.recorded_at
                    current_stop = (telemetry.recorded_at - stop_start).total_seconds() / 60
                else:
                    if current_stop > longest_stop:
                        longest_stop = current_stop
                    stop_start = None
                    current_stop = 0

            if self.speed == 0 and current_stop > longest_stop:
                longest_stop = current_stop

            if longest_stop > 30:
                create_or_refresh_alert(
                    alert_type='IDLE_TOO_LONG',
                    severity='WARNING',
                    message=f"Arrêt prolongé: {longest_stop:.0f} minutes sans mouvement",
                    value=longest_stop,
                    threshold=30,
                    cooldown_minutes=60,
                    use_mission=True
                )

        if self.speed > 90:
            create_or_refresh_alert(
                alert_type='SPEEDING',
                severity='WARNING',
                message=f"Excès de vitesse: {self.speed:.1f} km/h",
                value=self.speed,
                threshold=90,
                cooldown_minutes=15,
                use_mission=True
            )

        if self.gps_signal < 30:
            create_or_refresh_alert(
                alert_type='GPS_LOST',
                severity='WARNING',
                message=f"Signal GPS faible: {self.gps_signal}%",
                value=self.gps_signal,
                threshold=30,
                cooldown_minutes=10,
                use_mission=False
            )

    def calculate_distance(self, previous_telemetry):
        from math import radians, sin, cos, sqrt, atan2

        lat1, lon1 = radians(previous_telemetry.latitude), radians(previous_telemetry.longitude)
        lat2, lon2 = radians(self.latitude), radians(self.longitude)

        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return 6371 * c


# ========================
# ROUTE CHECKPOINT
# ========================
class RouteCheckpoint(models.Model):
    """Points de passage prédéfinis pour vérifier l'itinéraire"""
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='checkpoints')
    sequence = models.IntegerField()
    name = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    expected_arrival_minutes = models.IntegerField()
    allowed_deviation_meters = models.FloatField(default=500)

    actual_arrival_time = models.DateTimeField(null=True, blank=True)
    passed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.mission.truck.matricule} - {self.name}"


# ========================
# FUEL CONSUMPTION LOG
# ========================
class FuelConsumptionLog(models.Model):
    """Journal de consommation de carburant"""
    truck = models.ForeignKey(Truck, on_delete=models.CASCADE, related_name='fuel_logs')
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='fuel_logs', null=True, blank=True)

    recorded_at = models.DateTimeField(auto_now_add=True)
    fuel_level_before = models.FloatField()
    fuel_level_after = models.FloatField()
    fuel_consumed = models.FloatField()
    distance_traveled = models.FloatField()
    consumption_rate = models.FloatField(help_text="L/100km")

    def __str__(self):
        return f"{self.truck.matricule} - {self.consumption_rate:.2f} L/100km"


# ========================
# TRUCK ALERT
# ========================
class TruckAlert(models.Model):
    """Alertes générées pour les camions et anomalies station"""
    ALERT_TYPE_CHOICES = [
        ('LOW_FUEL', 'Carburant faible'),
        ('DEVIATION', 'Déviation'),
        ('OFF_ROUTE', 'Hors route'),
        ('DELAY', 'Retard'),
        ('BREAKDOWN', 'Panne'),
        ('MAINTENANCE', 'Maintenance'),
        ('MAINTENANCE_DUE', 'Maintenance due'),
        ('FUEL_LEAK', 'Fuite carburant'),
        ('HIGH_WATER', 'Niveau d’eau élevé'),
        ('SENSOR_FAIL', 'Capteur défaillant'),
        ('SPEEDING', 'Excès de vitesse'),
        ('IDLE_TOO_LONG', 'Arrêt prolongé'),
        ('GPS_LOST', 'Perte de signal GPS'),
    ]

    SEVERITY_CHOICES = [
        ('INFO', 'Information'),
        ('WARNING', 'Alerte'),
        ('CRITICAL', 'Critique'),
    ]

    truck = models.ForeignKey(Truck, on_delete=models.CASCADE, related_name='alerts', null=True, blank=True)
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='alerts', null=True, blank=True)
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    message = models.TextField()
    value = models.FloatField(null=True, blank=True)
    threshold = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['alert_type', 'resolved', 'created_at']),
            models.Index(fields=['truck', 'resolved', 'created_at']),
        ]

    def __str__(self):
        if self.truck:
            return f"{self.truck.matricule} - {self.alert_type}"
        return f"{self.alert_type} - station/system"

    def resolve(self):
        self.resolved = True
        self.resolved_at = timezone.now()
        self.save(update_fields=['resolved', 'resolved_at'])


# ========================
# DEPOT PRODUCT STOCK
# ========================
class DepotProductStock(models.Model):
    """Stock de produits dans un dépôt"""
    PRODUCT_CHOICES = [
        ('JET', 'JET'),
        ('SSP', 'SSP'),
        ('GAZOIL', 'Gazoil'),
    ]

    depot = models.ForeignKey(Depot, on_delete=models.CASCADE, related_name='product_stocks')
    product = models.CharField(max_length=20, choices=PRODUCT_CHOICES)
    current_volume = models.FloatField(default=0)
    max_capacity = models.FloatField(default=0)
    min_threshold = models.FloatField(default=0, help_text="Seuil minimum d'alerte")
    last_arrival_date = models.DateTimeField(null=True, blank=True, help_text="Date of last product arrival")
    updated_at = models.DateTimeField(auto_now=True)

    def fill_percentage(self):
        if self.max_capacity > 0:
            return (self.current_volume / self.max_capacity) * 100
        return 0

    class Meta:
        unique_together = ('depot', 'product')

    def __str__(self):
        return f"{self.depot.name} - {self.product}"


# ========================
# DEPOT STOCK COMPARISON
# ========================
class DepotStockComparison(models.Model):
    """Comparaison entre mesures manuelles et capteurs - seulement la dernière valeur"""
    depot = models.ForeignKey(Depot, on_delete=models.CASCADE, related_name='stock_comparisons')
    product = models.CharField(max_length=20)
    manual_volume = models.FloatField()
    sensor_volume = models.FloatField()
    variance = models.FloatField()
    variance_percent = models.FloatField()
    comparison_date = models.DateTimeField(auto_now_add=True)
    alert_level = models.CharField(max_length=20, default='NORMAL')

    class Meta:
        unique_together = ('depot', 'product')

    def __str__(self):
        return f"{self.depot.name} - {self.product} - {self.comparison_date.date()}"

    @classmethod
    def update_comparison(cls, depot, product, manual_volume, sensor_volume):
        variance = manual_volume - sensor_volume
        variance_percent = (variance / sensor_volume * 100) if sensor_volume > 0 else 0

        alert_level = 'NORMAL'
        if abs(variance_percent) > 10:
            alert_level = 'CRITICAL'
        elif abs(variance_percent) > 5:
            alert_level = 'WARNING'

        comparison, _ = cls.objects.update_or_create(
            depot=depot,
            product=product,
            defaults={
                'manual_volume': manual_volume,
                'sensor_volume': sensor_volume,
                'variance': variance,
                'variance_percent': variance_percent,
                'alert_level': alert_level,
            }
        )
        return comparison


# ========================
# STATION TANK
# ========================
class StationTank(models.Model):
    """Cuve de station-service"""
    PRODUCT_CHOICES = [
        ('JET', 'JET'),
        ('SSP', 'SSP'),
        ('GAZOIL', 'Gazoil'),
    ]

    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='tanks')
    tank_name = models.CharField(max_length=50)
    product = models.CharField(max_length=20, choices=PRODUCT_CHOICES)
    max_capacity = models.FloatField()
    current_volume = models.FloatField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.station.name} - {self.tank_name}"


# ========================
# STATION TLS SNAPSHOT
# ========================
class StationTLSSnapshot(models.Model):
    """Snapshot TLS des cuves"""
    SENSOR_STATUS_CHOICES = [
        ('OK', 'OK'),
        ('WARNING', 'Warning'),
        ('FAIL', 'Fail'),
    ]

    station_tank = models.ForeignKey(StationTank, on_delete=models.CASCADE, related_name='tls_snapshots')
    current_volume = models.FloatField()
    temperature = models.FloatField()
    water_level = models.FloatField()
    sensor_status = models.CharField(max_length=20, choices=SENSOR_STATUS_CHOICES, default='OK')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.station_tank} - TLS Snapshot"


# ========================
# DEPOT ARRIVAL
# ========================
class DepotArrival(models.Model):
    """Arrivées de produits au dépôt"""
    PRODUCT_CHOICES = [
        ('JET', 'JET'),
        ('SSP', 'SSP'),
        ('GAZOIL', 'Gazoil'),
    ]

    QUALITY_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    depot = models.ForeignKey(Depot, on_delete=models.CASCADE, related_name='arrivals')
    product = models.CharField(max_length=20, choices=PRODUCT_CHOICES)
    planned_volume = models.FloatField()
    received_volume = models.FloatField(null=True, blank=True)
    arrival_date = models.DateTimeField()
    supplier = models.CharField(max_length=100, blank=True, default='')
    quality_status = models.CharField(max_length=20, choices=QUALITY_STATUS_CHOICES, default='PENDING')
    notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"{self.depot.name} - {self.product} - {self.arrival_date.date()}"


# ========================
# QUALITY SAMPLE
# ========================
class QualitySample(models.Model):
    """Échantillons qualité"""
    RESULT_CHOICES = [
        ('CONFORME', 'Conforme'),
        ('NON_CONFORME', 'Non conforme'),
    ]

    arrival = models.ForeignKey(DepotArrival, on_delete=models.CASCADE, related_name='samples')
    sample_code = models.CharField(max_length=50)
    density = models.FloatField()
    temperature = models.FloatField()
    water_content = models.FloatField(default=0)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES)
    analyzed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sample_code} - {self.result}"


# ========================
# INCIDENT
# ========================
class Incident(models.Model):
    """Incidents enregistrés"""
    TYPE_CHOICES = [
        ('DELAY', 'Retard'),
        ('BREAKDOWN', 'Panne'),
        ('DEVIATION', 'Sortie route'),
        ('STOP', 'Arrêt'),
        ('ACCIDENT', 'Accident'),
        ('FUEL_LEAK', 'Fuite carburant'),
        ('SPEEDING', 'Excès vitesse'),
    ]

    SEVERITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical'),
    ]

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    truck = models.ForeignKey(Truck, on_delete=models.CASCADE, null=True, blank=True, related_name='incidents')
    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, null=True, blank=True, related_name='incidents')
    station = models.ForeignKey(Station, on_delete=models.CASCADE, null=True, blank=True, related_name='incidents')

    description = models.TextField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True, default='')

    def __str__(self):
        return f"{self.type} - {self.severity} - {self.created_at}"


# ========================
# MISSION EVENT
# ========================
class MissionEvent(models.Model):
    EVENT_TYPES = [
        ('LOADING_START', 'Loading Started'),
        ('DEPARTURE', 'Departure'),
        ('STOP_START', 'Stop Start'),
        ('STOP_END', 'Stop End'),
        ('BREAKDOWN', 'Breakdown'),
        ('MAINTENANCE', 'Maintenance'),
        ('FUEL_LEAK', 'Fuel Leak'),
        ('ARRIVAL', 'Arrival'),
    ]

    mission = models.ForeignKey(Mission, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    description = models.TextField(blank=True, default='')
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.mission} - {self.get_event_type_display()} - {self.timestamp}"



