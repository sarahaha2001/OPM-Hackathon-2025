import folium
from datetime import datetime
import random

# Generate dummy incident data
def generate_incidents(count=15):
    types = ['Near Miss', 'Accident', 'Environmental', 'Safety Observation']
    descriptions = [
        'Minor slip near scaffold',
        'Equipment failure',
        'Oil spill detected',
        'Unsafe PPE usage',
        'Dust level exceeded',
        'Fire alarm triggered'
    ]

    incidents = []
    for i in range(count):
        incident = {
            'id': i,
            'type': random.choice(types),
            'description': random.choice(descriptions),
            'latitude': 5 + random.uniform(0, 2),     # Roughly Guyana range
            'longitude': -61 + random.uniform(0, 4),
            'timestamp': datetime.now().isoformat()
        }
        incidents.append(incident)
    return incidents

# Generate incidents
incidents = generate_incidents()

# Create map with multiple style layers
incident_map = folium.Map(location=[5.5, -59.5], zoom_start=6, control_scale=True)

# Base map layers
folium.TileLayer(
    tiles='https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attr='&copy; OpenStreetMap contributors',
    name='Default'
).add_to(incident_map)

folium.TileLayer(
    tiles='https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    attr='&copy; CartoDB',
    name='Light Mode',
    control=True
).add_to(incident_map)

folium.TileLayer(
    tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attr='&copy; CartoDB',
    name='Dark Mode',
    control=True
).add_to(incident_map)


folium.TileLayer(
    tiles='https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attr='Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap (CC-BY-SA)',
    name='Terrain'
).add_to(incident_map)


# Add incident markers
for incident in incidents:
    popup_text = f"<strong>{incident['type']}</strong><br>{incident['description']}<br><small>{incident['timestamp']}</small>"
    folium.Marker(
        location=[incident['latitude'], incident['longitude']],
        popup=popup_text,
        icon=folium.Icon(color='red', icon='info-sign')
    ).add_to(incident_map)

# Add layer control
folium.LayerControl(collapsed=False).add_to(incident_map)

# Save to file
incident_map.save("incident_map_with_views.html")
print("Map successfully saved as incident_map_with_views.html")
