from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from logistics.models import (
    Depot,
    DepotProductStock,
    Station,
    StationTank,
    StationTLSSnapshot,
    Driver,
    Truck,
    Mission,
    TruckTelemetry,
    Incident,
)


class Command(BaseCommand):
    help = "Seed demo data for Control Tower logistics"

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Cleaning old demo data..."))

        TruckTelemetry.objects.all().delete()
        StationTLSSnapshot.objects.all().delete()
        StationTank.objects.all().delete()
        DepotProductStock.objects.all().delete()
        Incident.objects.all().delete()
        Mission.objects.all().delete()
        Truck.objects.all().delete()
        Driver.objects.all().delete()
        Station.objects.all().delete()
        Depot.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Old demo data removed."))

        # ========================
        # DEPOTS
        # ========================
        depot_moh = Depot.objects.create(
            name="Dépôt Mohammedia",
            city="Mohammedia",
            capacity_total=1200000,
            capacity_available=780000,
        )

        depot_mrk = Depot.objects.create(
            name="Dépôt Marrakech",
            city="Marrakech",
            capacity_total=900000,
            capacity_available=520000,
        )

        # Depot product stocks
        depot_stocks = [
            (depot_moh, "JET", 220000, 300000),
            (depot_moh, "SSP", 250000, 350000),
            (depot_moh, "GAZOIL", 310000, 550000),
            (depot_mrk, "JET", 120000, 180000),
            (depot_mrk, "SSP", 140000, 250000),
            (depot_mrk, "GAZOIL", 260000, 470000),
        ]

        for depot, product, current_volume, max_capacity in depot_stocks:
            DepotProductStock.objects.create(
                depot=depot,
                product=product,
                current_volume=current_volume,
                max_capacity=max_capacity,
            )

        # ========================
        # STATIONS
        # ========================
        stations_data = [
            ("Afriquia Casa Centre", "Casablanca", "Casablanca-Settat", "WARNING", 18000),
            ("Afriquia Rabat Agdal", "Rabat", "Rabat-Salé-Kénitra", "NORMAL", 12000),
            ("Afriquia Kénitra", "Kénitra", "Rabat-Salé-Kénitra", "NORMAL", 10000),
            ("Afriquia Tanger Route Port", "Tanger", "Tanger-Tétouan-Al Hoceïma", "WARNING", 15000),
            ("Afriquia Marrakech Centre", "Marrakech", "Marrakech-Safi", "NORMAL", 14000),
            ("Afriquia Agadir Sud", "Agadir", "Souss-Massa", "CRITICAL", 16000),
            ("Afriquia El Jadida", "El Jadida", "Casablanca-Settat", "NORMAL", 9000),
            ("Afriquia Fès", "Fès", "Fès-Meknès", "WARNING", 13000),
        ]

        stations = []
        for name, city, region, risk_level, daily_consumption in stations_data:
            station = Station.objects.create(
                name=name,
                city=city,
                region=region,
                stock={},
                daily_consumption=daily_consumption,
                risk_level=risk_level,
            )
            stations.append(station)

        # ========================
        # STATION TANKS + TLS SNAPSHOTS
        # ========================
        for station in stations:
            tank_ssp = StationTank.objects.create(
                station=station,
                tank_name="Tank SSP",
                product="SSP",
                max_capacity=40000,
            )
            tank_gazoil = StationTank.objects.create(
                station=station,
                tank_name="Tank Gazoil",
                product="GAZOIL",
                max_capacity=50000,
            )

            # Valeurs initiales réalistes
            if station.risk_level == "CRITICAL":
                ssp_volume = 5000
                gazoil_volume = 7000
                sensor_status = "WARNING"
            elif station.risk_level == "WARNING":
                ssp_volume = 12000
                gazoil_volume = 15000
                sensor_status = "OK"
            else:
                ssp_volume = 22000
                gazoil_volume = 28000
                sensor_status = "OK"

            StationTLSSnapshot.objects.create(
                station_tank=tank_ssp,
                current_volume=ssp_volume,
                temperature=24.5,
                water_level=2.0,
                sensor_status=sensor_status,
            )

            StationTLSSnapshot.objects.create(
                station_tank=tank_gazoil,
                current_volume=gazoil_volume,
                temperature=23.8,
                water_level=1.0,
                sensor_status=sensor_status,
            )

        # ========================
        # DRIVERS
        # ========================
        drivers = [
            Driver.objects.create(name="Ahmed Benali", cin="AB123456", phone="0600000001", rating=4.7),
            Driver.objects.create(name="Youssef Tazi", cin="YT223344", phone="0600000002", rating=4.5),
            Driver.objects.create(name="Hicham Alaoui", cin="HA556677", phone="0600000003", rating=4.3),
            Driver.objects.create(name="Karim Mansouri", cin="KM998877", phone="0600000004", rating=4.8),
        ]

        # ========================
        # TRUCKS
        # ========================
        trucks = [
            Truck.objects.create(
                matricule="23456-A-1",
                transporter="TransFuel Maroc",
                driver=drivers[0],
                status="ON_ROUTE",
                current_lat=33.75,
                current_lng=-7.35,
            ),
            Truck.objects.create(
                matricule="34567-B-2",
                transporter="Atlas Logistique",
                driver=drivers[1],
                status="DELAYED",
                current_lat=33.90,
                current_lng=-6.85,
            ),
            Truck.objects.create(
                matricule="45678-C-3",
                transporter="Sahara Transport",
                driver=drivers[2],
                status="STOPPED",
                current_lat=31.85,
                current_lng=-7.95,
            ),
            Truck.objects.create(
                matricule="56789-D-4",
                transporter="Maghreb Mobility",
                driver=drivers[3],
                status="ON_ROUTE",
                current_lat=30.60,
                current_lng=-9.30,
            ),
        ]

        # ========================
        # MISSIONS
        # ========================
        now = timezone.now()

        missions = [
            Mission.objects.create(
                truck=trucks[0],
                depot=depot_moh,
                station=stations[0],  # Casa
                product="GAZOIL",
                quantity=12000,
                departure_time=now - timedelta(hours=1, minutes=10),
                eta=now + timedelta(minutes=30),
                delivered_quantity=None,
                status="IN_TRANSIT",
            ),
            Mission.objects.create(
                truck=trucks[1],
                depot=depot_moh,
                station=stations[1],  # Rabat
                product="SSP",
                quantity=10000,
                departure_time=now - timedelta(hours=2),
                eta=now - timedelta(minutes=20),
                delivered_quantity=None,
                status="IN_TRANSIT",
            ),
            Mission.objects.create(
                truck=trucks[2],
                depot=depot_mrk,
                station=stations[4],  # Marrakech
                product="GAZOIL",
                quantity=15000,
                departure_time=now - timedelta(hours=1, minutes=30),
                eta=now + timedelta(minutes=40),
                delivered_quantity=None,
                status="IN_TRANSIT",
            ),
            Mission.objects.create(
                truck=trucks[3],
                depot=depot_mrk,
                station=stations[5],  # Agadir
                product="SSP",
                quantity=13000,
                departure_time=now - timedelta(hours=3),
                eta=now + timedelta(minutes=10),
                delivered_quantity=None,
                status="IN_TRANSIT",
            ),
        ]

        # ========================
        # TELEMETRY
        # ========================
        telemetry_data = [
            (trucks[0], missions[0], 33.75, -7.35, 62, 90, 45, "IN_TRANSIT"),
            (trucks[1], missions[1], 33.90, -6.85, 25, 40, 80, "ALERT"),
            (trucks[2], missions[2], 31.85, -7.95, 0, 0, 35, "STOPPED"),
            (trucks[3], missions[3], 30.60, -9.30, 58, 180, 72, "IN_TRANSIT"),
        ]

        for truck, mission, lat, lng, speed, heading, progress, status in telemetry_data:
            TruckTelemetry.objects.create(
                truck=truck,
                mission=mission,
                latitude=lat,
                longitude=lng,
                speed=speed,
                heading=heading,
                progress=progress,
                status=status,
            )

        # ========================
        # INCIDENTS
        # ========================
        Incident.objects.create(
            type="DELAY",
            truck=trucks[1],
            station=stations[1],
            description="Retard détecté sur livraison Rabat Agdal",
            severity="CRITICAL",
        )

        Incident.objects.create(
            type="STOP",
            truck=trucks[2],
            station=stations[4],
            description="Camion à l’arrêt non planifié près de Marrakech",
            severity="MEDIUM",
        )

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))