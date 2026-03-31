from django import forms
from .models import Mission, Truck, Station, Depot, Driver

class MissionForm(forms.ModelForm):
    class Meta:
        model = Mission
        fields = [
            'truck', 'depot', 'station', 
            'total_distance_km', 'estimated_duration_minutes',
            'departure_time', 'eta', 
            'status', 'notes'
        ]
        widgets = {
            'departure_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'eta': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

class TruckForm(forms.ModelForm):
    driver = forms.ModelChoiceField(queryset=Driver.objects.all(), required=True)

    class Meta:
        model = Truck
        fields = [
            'matricule', 'transporter', 'brand', 'model', 'year',
            'driver', 'capacity_total', 'max_compartment_count',
            'fuel_tank_capacity', 'fuel_level', 'fuel_consumption_per_km', 'fuel_consumption_idle',
            'total_odometer', 'trip_odometer', 'last_maintenance_km', 'next_maintenance_km',
            'status', 'current_lat', 'current_lng',
            'last_fuel_refill', 'last_maintenance'
        ]
        widgets = {
            'last_fuel_refill': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'last_maintenance': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

class StationForm(forms.ModelForm):
    class Meta:
        model = Station
        fields = [
            'name', 'city', 'region', 'address', 
            'latitude', 'longitude', 'daily_consumption',
            'risk_level'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
        }


# logistics/forms.py

from .models import Depot

class DepotForm(forms.ModelForm):
    class Meta:
        model = Depot
        fields = [
            'name', 'city', 'capacity_total', 'address',
            'latitude', 'longitude'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 2}),
        }