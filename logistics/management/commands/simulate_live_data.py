# management/commands/simulate_live_data.py

import random
import time
import math
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from logistics.models import (
    Truck, TruckTelemetry, Mission, Depot, Station, StationTank, StationTLSSnapshot,
    DepotProductStock, DepotArrival, QualitySample, DepotStockComparison, TruckAlert,
    FuelConsumptionLog, MissionEvent
)

SIMULATION_INTERVAL = 10
BASE_SPEED_KPH = 70
SPEED_VARIATION = 20
DEVIATION_BASE_PROBABILITY = 0.05
DEVIATION_MAX_KM = 5.0
STOP_PROBABILITY = 0.02
STOP_DURATION_ITERATIONS = 3
BREAKDOWN_PROBABILITY = 0.001
BREAKDOWN_DURATION_ITERATIONS = 30
MAINTENANCE_PROBABILITY = 0.0005
MAINTENANCE_DURATION_ITERATIONS = 20
FUEL_LEAK_PROBABILITY = 0.0002
FUEL_LEAK_EXTRA_LOSS_FACTOR = 0.3
TRAFFIC_CHANGE_PROBABILITY = 0.1
TRAFFIC_FACTOR_MIN = 0.5
TRAFFIC_FACTOR_MAX = 1.5
WEATHER_CHANGE_PROBABILITY = 0.05
WEATHER_FACTOR_MIN = 0.6
WEATHER_FACTOR_MAX = 1.0
CONSUMPTION_RATE_L_PER_100KM = 35
LOW_FUEL_THRESHOLD_PERCENT = 15
LOW_FUEL_COOLDOWN_SECONDS = 1800
DEVIATION_ALERT_COOLDOWN_SECONDS = 1800
DELAY_ALERT_COOLDOWN_SECONDS = 900
IDLE_ALERT_COOLDOWN_SECONDS = 3600
STOPPED_THRESHOLD_ITERATIONS = 3
STOPPED_ALERT_COOLDOWN_SECONDS = 3600
BREAKDOWN_ALERT_COOLDOWN_SECONDS = 600
MAINTENANCE_ALERT_COOLDOWN_SECONDS = 3600
FUEL_LEAK_ALERT_COOLDOWN_SECONDS = 3600
HIGH_WATER_THRESHOLD = 0.1
TLS_ANOMALY_ALERT_COOLDOWN_SECONDS = 1800

ARRIVAL_DAYS_BASE = 15
ARRIVAL_FORCE_DAYS = 30

CRITICAL_DAYS = 1
WARNING_DAYS = 2
CRITICAL_VOLUME_LITERS = 1000

PRODUCT_CONSUMPTION_FACTOR = {
    'JET': 1.2,
    'SSP': 1.0,
    'GAZOIL': 0.8,
}

PRODUCT_CAPACITY_SHARE = {
    'JET': 0.50,
    'SSP': 0.30,
    'GAZOIL': 0.20,
}

TELEMETRY_RETENTION_HOURS = 6
CLEANUP_INTERVAL_ITERATIONS = 360


class Command(BaseCommand):
    help = 'Simulate real-time logistics data for control tower dashboard'

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Run only one iteration and exit',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting live data simulation...'))
        self.init_simulation()
        self.iteration_count = 0
        self.run_simulation(options['once'])

    def init_simulation(self):
        self.active_trucks = {}
        missions = Mission.objects.filter(
            status__in=['LOADING', 'IN_TRANSIT']
        ).select_related('truck', 'depot', 'station', 'truck__driver')

        for mission in missions:
            truck = mission.truck
            start = (mission.depot.latitude, mission.depot.longitude)
            end = (mission.station.latitude, mission.station.longitude)

            total_distance = mission.total_distance_km
            if not total_distance:
                total_distance = self.haversine_distance(start, end)
                mission.total_distance_km = total_distance
                mission.save(update_fields=['total_distance_km'])

            traveled = mission.traveled_distance_km or 0.0

            self.active_trucks[truck.id] = {
                'truck': truck,
                'mission': mission,
                'start': start,
                'end': end,
                'total_distance': total_distance,
                'traveled': traveled,
                'last_update': timezone.now(),
                'stop_remaining': 0,
                'breakdown_remaining': 0,
                'maintenance_remaining': 0,
                'traffic_factor': 1.0,
                'weather_factor': 1.0,
                'speed': BASE_SPEED_KPH,
                'deviation_km': 0.0,
                'route_status': 'ON_TRACK',
                'stop_counter': 0,
                'fuel_leak_active': False,
                'stopped_since': None,
                'departure_logged': False,
                'loading_started': False,
            }

        self.ensure_depot_capacities()
        self.weather_factor = 1.0

    def ensure_depot_capacities(self):
        for depot in Depot.objects.all():
            for product, share in PRODUCT_CAPACITY_SHARE.items():
                max_cap = depot.capacity_total * share
                DepotProductStock.objects.get_or_create(
                    depot=depot,
                    product=product,
                    defaults={
                        'current_volume': 0,
                        'max_capacity': max_cap,
                        'min_threshold': 0,
                    }
                )
            for stock in depot.product_stocks.all():
                share = PRODUCT_CAPACITY_SHARE.get(stock.product, 0)
                expected_max = depot.capacity_total * share
                if stock.max_capacity != expected_max:
                    stock.max_capacity = expected_max
                    stock.save(update_fields=['max_capacity'])

    def run_simulation(self, once):
        try:
            while True:
                self.simulate_step()
                if once:
                    break
                time.sleep(SIMULATION_INTERVAL)
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS('Simulation stopped.'))

    def simulate_step(self):
        now = timezone.now()
        if random.random() < WEATHER_CHANGE_PROBABILITY:
            change = random.uniform(-0.1, 0.1)
            self.weather_factor = max(
                WEATHER_FACTOR_MIN,
                min(WEATHER_FACTOR_MAX, self.weather_factor + change)
            )

        with transaction.atomic():
            self.simulate_trucks(now)
            self.simulate_depots(now)
            self.simulate_stations(now)

        self.iteration_count += 1
        if self.iteration_count % CLEANUP_INTERVAL_ITERATIONS == 0:
            self.cleanup_old_telemetry()

        self.compute_global_kpis()
        self.stdout.write(
            f'Iteration {self.iteration_count} at {now.strftime("%H:%M:%S")} | '
            f'Active trucks: {len(self.active_trucks)} | '
            f'Weather factor: {self.weather_factor:.2f}'
        )

    def simulate_trucks(self, now):
        for truck_id, state in list(self.active_trucks.items()):
            mission = state['mission']
            truck = state['truck']
            elapsed = (now - state['last_update']).total_seconds()
            if elapsed <= 0:
                continue

            driver_rating = truck.driver.rating if truck.driver else 3.0
            driver_factor = 0.8 + (driver_rating / 5) * 0.4

            traffic = state['traffic_factor']
            weather = self.weather_factor
            combined_factor = traffic * weather * driver_factor

            speed = 0
            breakdown_occurred = False
            maintenance_occurred = False

            if state['breakdown_remaining'] > 0:
                state['breakdown_remaining'] -= 1
                speed = 0
            elif state['maintenance_remaining'] > 0:
                state['maintenance_remaining'] -= 1
                speed = 0
            elif state['stop_remaining'] > 0:
                state['stop_remaining'] -= 1
                speed = 0
                if state['stop_remaining'] == 0 and state.get('stopped_since'):
                    self.log_mission_event(mission, 'STOP_END', "Resumed after stop")
                    state['stopped_since'] = None
            else:
                if random.random() < STOP_PROBABILITY:
                    state['stop_remaining'] = STOP_DURATION_ITERATIONS
                    speed = 0
                    state['stopped_since'] = now
                    self.log_mission_event(mission, 'STOP_START', "Truck stopped")
                elif random.random() < BREAKDOWN_PROBABILITY:
                    state['breakdown_remaining'] = BREAKDOWN_DURATION_ITERATIONS
                    speed = 0
                    breakdown_occurred = True
                    self.log_mission_event(mission, 'BREAKDOWN', "Breakdown occurred")
                elif random.random() < MAINTENANCE_PROBABILITY:
                    state['maintenance_remaining'] = MAINTENANCE_DURATION_ITERATIONS
                    speed = 0
                    maintenance_occurred = True
                    self.log_mission_event(mission, 'MAINTENANCE', "Scheduled maintenance")
                else:
                    speed = BASE_SPEED_KPH + random.uniform(-SPEED_VARIATION, SPEED_VARIATION)
                    speed = max(0, speed * combined_factor)
                    if not state.get('departure_logged') and speed > 0 and state.get('loading_started'):
                        self.log_mission_event(mission, 'DEPARTURE', "Truck departed from depot")
                        state['departure_logged'] = True

            state['speed'] = speed

            fuel_level = truck.fuel_level
            if fuel_level <= 0:
                speed = 0
                state['speed'] = 0
                self.create_alert_with_cooldown(
                    truck=truck,
                    mission=mission,
                    alert_type='LOW_FUEL',
                    severity='CRITICAL',
                    message="Fuel empty – truck stopped",
                    value=0,
                    threshold=LOW_FUEL_THRESHOLD_PERCENT,
                    cooldown_seconds=LOW_FUEL_COOLDOWN_SECONDS,
                    now=now
                )

            distance_inc = speed * elapsed / 3600
            new_traveled = state['traveled'] + distance_inc
            remaining = max(0, state['total_distance'] - new_traveled)

            if remaining <= 0:
                final_lat, final_lng = state['end']
                progress = 100.0
                self.create_telemetry(
                    truck, mission, final_lat, final_lng, speed,
                    remaining, progress, state['deviation_km'], state['route_status']
                )
                mission.status = 'ARRIVED'
                mission.actual_arrival_time = now
                mission.traveled_distance_km = state['total_distance']
                mission.remaining_distance_km = 0
                mission.eta_minutes = 0
                mission.eta = now
                mission.save(update_fields=[
                    'status', 'actual_arrival_time', 'traveled_distance_km',
                    'remaining_distance_km', 'eta_minutes', 'eta'
                ])
                self.log_mission_event(mission, 'ARRIVAL', "Truck arrived at station")
                truck.status = 'AVAILABLE'
                truck.save(update_fields=['status'])
                del self.active_trucks[truck_id]
                continue

            fraction = new_traveled / state['total_distance'] if state['total_distance'] > 0 else 0
            lat, lng = self.interpolate_position(state['start'], state['end'], fraction)
            progress = (new_traveled / state['total_distance']) * 100 if state['total_distance'] > 0 else 0

            deviation_prob = DEVIATION_BASE_PROBABILITY * (1 + (1 - driver_rating / 5) * 0.5)
            if random.random() < deviation_prob:
                state['deviation_km'] = min(
                    DEVIATION_MAX_KM,
                    state['deviation_km'] + random.uniform(0.1, 1.0)
                )
            else:
                state['deviation_km'] = max(0, state['deviation_km'] - random.uniform(0, 0.2))

            deviation = state['deviation_km']
            if deviation < 1:
                route_status = 'ON_TRACK'
            elif deviation <= 5:
                route_status = 'DEVIATION'
            else:
                route_status = 'OFF_ROUTE'
            state['route_status'] = route_status

            mission.remaining_distance_km = remaining
            mission.traveled_distance_km = new_traveled
            if speed > 0:
                eta_minutes = int((remaining / speed) * 60)
                mission.eta_minutes = eta_minutes
                mission.eta = now + timedelta(minutes=eta_minutes)
            else:
                mission.eta_minutes = None
                mission.eta = None
            mission.save(update_fields=[
                'remaining_distance_km', 'traveled_distance_km', 'eta_minutes', 'eta'
            ])

            fuel_consumed_base = (CONSUMPTION_RATE_L_PER_100KM * distance_inc) / 100 if distance_inc > 0 else 0
            fuel_consumed = fuel_consumed_base

            if not state['fuel_leak_active'] and random.random() < FUEL_LEAK_PROBABILITY and distance_inc > 0:
                extra_loss = fuel_consumed_base * FUEL_LEAK_EXTRA_LOSS_FACTOR
                fuel_consumed += extra_loss
                state['fuel_leak_active'] = True
                self.create_alert_with_cooldown(
                    truck=truck,
                    mission=mission,
                    alert_type='FUEL_LEAK',
                    severity='CRITICAL',
                    message=f"Fuel leak detected: extra loss {extra_loss:.1f} L",
                    value=extra_loss,
                    threshold=0,
                    cooldown_seconds=FUEL_LEAK_ALERT_COOLDOWN_SECONDS,
                    now=now
                )
                self.log_mission_event(mission, 'FUEL_LEAK', f"Fuel leak: extra {extra_loss:.1f} L lost")

            if fuel_consumed > 0 and fuel_level > 0:
                fuel_before = truck.fuel_level
                fuel_consumed = min(fuel_consumed, fuel_before)
                fuel_after = fuel_before - fuel_consumed
                truck.fuel_level = max(0, fuel_after)
                truck.save(update_fields=['fuel_level'])

                if distance_inc > 0.01:
                    FuelConsumptionLog.objects.create(
                        truck=truck,
                        mission=mission,
                        fuel_level_before=fuel_before,
                        fuel_level_after=fuel_after,
                        fuel_consumed=fuel_consumed,
                        distance_traveled=distance_inc,
                        consumption_rate=CONSUMPTION_RATE_L_PER_100KM
                    )

                fuel_pct = (truck.fuel_level / truck.fuel_tank_capacity) * 100 if truck.fuel_tank_capacity else 0
                if fuel_pct < LOW_FUEL_THRESHOLD_PERCENT:
                    self.create_alert_with_cooldown(
                        truck=truck,
                        mission=mission,
                        alert_type='LOW_FUEL',
                        severity='CRITICAL',
                        message=f"Low fuel: {fuel_pct:.1f}% remaining",
                        value=fuel_pct,
                        threshold=LOW_FUEL_THRESHOLD_PERCENT,
                        cooldown_seconds=LOW_FUEL_COOLDOWN_SECONDS,
                        now=now
                    )

            truck.current_lat = lat
            truck.current_lng = lng
            truck.status = 'STOPPED' if speed == 0 else 'ON_ROUTE'
            truck.save(update_fields=['current_lat', 'current_lng', 'status'])

            if speed == 0:
                state['stop_counter'] += 1
                if state['stop_counter'] >= STOPPED_THRESHOLD_ITERATIONS:
                    self.create_alert_with_cooldown(
                        truck=truck,
                        mission=mission,
                        alert_type='IDLE_TOO_LONG',
                        severity='WARNING',
                        message=f"Truck stopped for {state['stop_counter'] * SIMULATION_INTERVAL} seconds",
                        value=state['stop_counter'] * SIMULATION_INTERVAL,
                        threshold=STOPPED_THRESHOLD_ITERATIONS * SIMULATION_INTERVAL,
                        cooldown_seconds=STOPPED_ALERT_COOLDOWN_SECONDS,
                        now=now
                    )
            else:
                state['stop_counter'] = 0

            if deviation > 5:
                self.create_alert_with_cooldown(
                    truck=truck,
                    mission=mission,
                    alert_type='OFF_ROUTE',
                    severity='CRITICAL',
                    message=f"Off route: deviation {deviation:.1f} km",
                    value=deviation,
                    threshold=5,
                    cooldown_seconds=DEVIATION_ALERT_COOLDOWN_SECONDS,
                    now=now
                )
            elif 1 <= deviation <= 5:
                self.create_alert_with_cooldown(
                    truck=truck,
                    mission=mission,
                    alert_type='DEVIATION',
                    severity='WARNING',
                    message=f"Route deviation: {deviation:.1f} km",
                    value=deviation,
                    threshold=1,
                    cooldown_seconds=DEVIATION_ALERT_COOLDOWN_SECONDS,
                    now=now
                )

            if mission.eta and mission.eta < now and mission.status not in ['COMPLETED', 'CANCELLED']:
                delay_minutes = (now - mission.eta).total_seconds() / 60
                self.create_alert_with_cooldown(
                    truck=truck,
                    mission=mission,
                    alert_type='DELAY',
                    severity='WARNING' if delay_minutes < 60 else 'CRITICAL',
                    message=f"Delay of {delay_minutes:.0f} minutes",
                    value=delay_minutes,
                    threshold=0,
                    cooldown_seconds=DELAY_ALERT_COOLDOWN_SECONDS,
                    now=now
                )

            if breakdown_occurred:
                self.create_alert_with_cooldown(
                    truck=truck,
                    mission=mission,
                    alert_type='BREAKDOWN',
                    severity='CRITICAL',
                    message="Truck breakdown – stopped for maintenance",
                    value=0,
                    threshold=0,
                    cooldown_seconds=BREAKDOWN_ALERT_COOLDOWN_SECONDS,
                    now=now
                )
            if maintenance_occurred:
                self.create_alert_with_cooldown(
                    truck=truck,
                    mission=mission,
                    alert_type='MAINTENANCE',
                    severity='WARNING',
                    message="Scheduled maintenance – short stop",
                    value=0,
                    threshold=0,
                    cooldown_seconds=MAINTENANCE_ALERT_COOLDOWN_SECONDS,
                    now=now
                )

            self.create_telemetry(
                truck, mission, lat, lng, speed,
                remaining, progress, deviation, route_status
            )

            state['traveled'] = new_traveled
            state['last_update'] = now

            if random.random() < TRAFFIC_CHANGE_PROBABILITY:
                change = random.uniform(-0.2, 0.2)
                state['traffic_factor'] = max(
                    TRAFFIC_FACTOR_MIN,
                    min(TRAFFIC_FACTOR_MAX, state['traffic_factor'] + change)
                )

            self.update_truck_health_score(truck, state)

    def create_telemetry(self, truck, mission, lat, lng, speed, remaining, progress, deviation, route_status):
        if speed == 0:
            telemetry_status = 'STOPPED'
        elif remaining <= 0:
            telemetry_status = 'ARRIVED'
        else:
            telemetry_status = 'IN_TRANSIT'

        return TruckTelemetry.objects.create(
            truck=truck,
            mission=mission,
            latitude=lat,
            longitude=lng,
            speed=speed,
            heading=0,
            remaining_distance_km=remaining,
            progress=progress,
            deviation_km=deviation,
            route_status=route_status,
            status=telemetry_status,
        )

    def create_alert_with_cooldown(self, truck, mission, alert_type, severity, message, value, threshold, cooldown_seconds, now):
        filters = {
            'alert_type': alert_type,
            'resolved': False,
            'created_at__gte': now - timedelta(seconds=cooldown_seconds),
        }

        if truck is not None:
            filters['truck'] = truck
        if mission is not None:
            filters['mission'] = mission

        last_alert = TruckAlert.objects.filter(**filters).first()

        if not last_alert:
            TruckAlert.objects.create(
                truck=truck,
                mission=mission,
                alert_type=alert_type,
                severity=severity,
                message=message,
                value=value,
                threshold=threshold,
            )

    def log_mission_event(self, mission, event_type, description):
        MissionEvent.objects.create(
            mission=mission,
            event_type=event_type,
            description=description,
            timestamp=timezone.now()
        )

    def update_truck_health_score(self, truck, state):
        fuel_pct = (truck.fuel_level / truck.fuel_tank_capacity) * 100 if truck.fuel_tank_capacity else 0
        fuel_score = min(30, max(0, (fuel_pct / 100) * 30))
        dev = state['deviation_km']
        deviation_score = max(0, 30 * (1 - min(1, dev / 5)))
        breakdown_score = 0 if state['breakdown_remaining'] > 0 or state['maintenance_remaining'] > 0 else 40
        score = fuel_score + deviation_score + breakdown_score
        state['health_score'] = score

    def simulate_depots(self, now):
        for depot in Depot.objects.all():
            for product in ['JET', 'SSP', 'GAZOIL']:
                stock, _ = DepotProductStock.objects.get_or_create(
                    depot=depot,
                    product=product,
                    defaults={
                        'current_volume': 0,
                        'max_capacity': depot.capacity_total * PRODUCT_CAPACITY_SHARE[product]
                    }
                )
                last_arrival = stock.last_arrival_date
                if last_arrival:
                    days_since = (now - last_arrival).total_seconds() / 86400
                else:
                    days_since = ARRIVAL_FORCE_DAYS + 1

                create_arrival = False
                if days_since > ARRIVAL_FORCE_DAYS:
                    create_arrival = True
                elif days_since > ARRIVAL_DAYS_BASE:
                    prob = (days_since - ARRIVAL_DAYS_BASE) / ARRIVAL_FORCE_DAYS
                    if random.random() < prob * 0.01:
                        create_arrival = True

                if create_arrival:
                    self.create_depot_arrival(depot, product, now)
                    stock.last_arrival_date = now
                    stock.save(update_fields=['last_arrival_date'])

            self.consume_depot_stock(depot)

    def create_depot_arrival(self, depot, product, now):
        planned_volume = random.uniform(10000, 50000)
        arrival = DepotArrival.objects.create(
            depot=depot,
            product=product,
            planned_volume=planned_volume,
            arrival_date=now,
            supplier='Simulated Supplier',
        )

        is_conforming = random.random() < 0.95
        result = 'CONFORME' if is_conforming else 'NON_CONFORME'
        QualitySample.objects.create(
            arrival=arrival,
            sample_code=f'SMP-{arrival.id}',
            density=random.uniform(0.82, 0.86),
            temperature=random.uniform(15, 25),
            water_content=random.uniform(0, 0.5),
            result=result,
        )

        if is_conforming:
            arrival.quality_status = 'APPROVED'
            arrival.received_volume = planned_volume
            arrival.save(update_fields=['quality_status', 'received_volume'])

            stock = DepotProductStock.objects.get(depot=depot, product=product)
            stock.current_volume += planned_volume
            if stock.current_volume > stock.max_capacity:
                stock.current_volume = stock.max_capacity
            stock.save(update_fields=['current_volume', 'updated_at'])

            sensor_volume = stock.current_volume * (1 + random.uniform(-0.05, 0.05))
            variance = stock.current_volume - sensor_volume
            variance_percent = (variance / sensor_volume) * 100 if sensor_volume else 0
            alert_level = 'NORMAL'
            if abs(variance_percent) > 10:
                alert_level = 'CRITICAL'
            elif abs(variance_percent) > 5:
                alert_level = 'WARNING'

            DepotStockComparison.objects.update_or_create(
                depot=depot,
                product=product,
                defaults={
                    'manual_volume': stock.current_volume,
                    'sensor_volume': sensor_volume,
                    'variance': variance,
                    'variance_percent': variance_percent,
                    'alert_level': alert_level,
                }
            )
        else:
            arrival.quality_status = 'REJECTED'
            arrival.received_volume = 0
            arrival.save(update_fields=['quality_status', 'received_volume'])

    def consume_depot_stock(self, depot):
        stocks = list(depot.product_stocks.all())
        if not stocks:
            return
        stock = random.choice(stocks)
        reduction = stock.current_volume * random.uniform(0, 0.05)
        stock.current_volume = max(0, stock.current_volume - reduction)
        stock.save(update_fields=['current_volume', 'updated_at'])

    def simulate_stations(self, now):
        for station in Station.objects.all():
            tanks = list(station.tanks.all())
            if not tanks:
                continue

            total_factor = sum(PRODUCT_CONSUMPTION_FACTOR.get(tank.product, 1.0) for tank in tanks)
            for tank in tanks:
                factor = PRODUCT_CONSUMPTION_FACTOR.get(tank.product, 1.0)
                share = factor / total_factor if total_factor else 0
                consumption_this_interval = station.daily_consumption * share * (SIMULATION_INTERVAL / 86400)
                consumption_this_interval *= random.uniform(0.8, 1.2)
                tank.current_volume = max(0, tank.current_volume - consumption_this_interval)
                tank.save(update_fields=['current_volume', 'last_updated'])

                water_level = random.uniform(0, 0.2)
                sensor_status = random.choices(['OK', 'WARNING', 'FAIL'], weights=[0.9, 0.08, 0.02])[0]

                StationTLSSnapshot.objects.create(
                    station_tank=tank,
                    current_volume=tank.current_volume,
                    temperature=random.uniform(15, 35),
                    water_level=water_level,
                    sensor_status=sensor_status,
                )

                if water_level > HIGH_WATER_THRESHOLD:
                    self.create_alert_with_cooldown(
                        truck=None,
                        mission=None,
                        alert_type='HIGH_WATER',
                        severity='WARNING',
                        message=f"High water level {water_level:.1%} in tank {tank.tank_name} at {station.name}",
                        value=water_level,
                        threshold=HIGH_WATER_THRESHOLD,
                        cooldown_seconds=TLS_ANOMALY_ALERT_COOLDOWN_SECONDS,
                        now=now
                    )

                if sensor_status == 'FAIL':
                    self.create_alert_with_cooldown(
                        truck=None,
                        mission=None,
                        alert_type='SENSOR_FAIL',
                        severity='CRITICAL',
                        message=f"Sensor failure on tank {tank.tank_name} at {station.name}",
                        value=0,
                        threshold=0,
                        cooldown_seconds=TLS_ANOMALY_ALERT_COOLDOWN_SECONDS,
                        now=now
                    )

            min_days = float('inf')
            low_volume_alert = False
            for tank in tanks:
                days = tank.current_volume / station.daily_consumption if station.daily_consumption > 0 else float('inf')
                min_days = min(min_days, days)
                if tank.current_volume < CRITICAL_VOLUME_LITERS:
                    low_volume_alert = True

            if low_volume_alert or min_days < CRITICAL_DAYS:
                station.risk_level = 'CRITICAL'
            elif min_days < WARNING_DAYS:
                station.risk_level = 'WARNING'
            else:
                station.risk_level = 'NORMAL'
            station.save(update_fields=['risk_level'])

    def compute_global_kpis(self):
        active_trucks = len(self.active_trucks)
        avg_speed = sum(state['speed'] for state in self.active_trucks.values()) / max(1, active_trucks)
        delayed = sum(
            1 for state in self.active_trucks.values()
            if state['mission'].eta and state['mission'].eta < timezone.now()
        )
        low_fuel = sum(
            1 for state in self.active_trucks.values()
            if state['truck'].fuel_tank_capacity and (
                state['truck'].fuel_level / state['truck'].fuel_tank_capacity * 100 < LOW_FUEL_THRESHOLD_PERCENT
            )
        )
        self.stdout.write(
            f"  KPIs: active={active_trucks}, avg_speed={avg_speed:.1f} km/h, "
            f"delayed={delayed}, low_fuel={low_fuel}"
        )

    def cleanup_old_telemetry(self):
        cutoff = timezone.now() - timedelta(hours=TELEMETRY_RETENTION_HOURS)
        deleted_count, _ = TruckTelemetry.objects.filter(recorded_at__lt=cutoff).delete()
        self.stdout.write(f"Cleaned up old telemetry: {deleted_count} records removed")

    def haversine_distance(self, coord1, coord2):
        lat1, lon1 = math.radians(coord1[0]), math.radians(coord1[1])
        lat2, lon2 = math.radians(coord2[0]), math.radians(coord2[1])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(min(1, math.sqrt(a)))
        return 6371 * c

    def interpolate_position(self, start, end, fraction):
        lat = start[0] + (end[0] - start[0]) * fraction
        lng = start[1] + (end[1] - start[1]) * fraction
        return lat, lng