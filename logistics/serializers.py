from rest_framework import serializers
from .models import Depot, Station, Driver, Truck, Mission, Incident


class DepotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Depot
        fields = '__all__'


class StationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Station
        fields = '__all__'


class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = '__all__'


class TruckSerializer(serializers.ModelSerializer):
    driver = DriverSerializer(read_only=True)

    class Meta:
        model = Truck
        fields = '__all__'


class MissionSerializer(serializers.ModelSerializer):
    truck = TruckSerializer(read_only=True)
    depot = DepotSerializer(read_only=True)
    station = StationSerializer(read_only=True)

    class Meta:
        model = Mission
        fields = '__all__'


class IncidentSerializer(serializers.ModelSerializer):
    truck = TruckSerializer(read_only=True)
    station = StationSerializer(read_only=True)

    class Meta:
        model = Incident
        fields = '__all__'