import { useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import { ALL_TOWNS, COORDS, AMENITIES } from '../constants';
import { scoreToColor } from '../engine';

function MapContent({ recs, highlightedTown }) {
  const map = useMap();
  const markersRef = useRef([]);
  const amenityMarkersRef = useRef([]);          // per-highlight amenity markers
  const sharedAmenityMarkersRef = useRef([]);    // all rec amenities markers
  const townMarkersRef = useRef({});

  const clearAmenityMarkers = useCallback(() => {
    amenityMarkersRef.current.forEach(m => map.removeLayer(m));
    amenityMarkersRef.current = [];
  }, [map]);

  const clearSharedAmenityMarkers = useCallback(() => {
    sharedAmenityMarkersRef.current.forEach(m => map.removeLayer(m));
    sharedAmenityMarkersRef.current = [];
  }, [map]);

  const showAmenityMarkers = useCallback((town) => {
    clearAmenityMarkers();
    const rec = recs.find(r => r.town === town);
    const c = rec?.centroid || COORDS[town];
    const amenities = rec?.amenities || {};
    const fallback = AMENITIES[town] || {};
    if (!c) return;

    const amenityDefs = [
      { key: 'mrt', icon: '🚇', color: '#3498db', label: amenities.mrt?.name || fallback.mrt || 'MRT Station', fallbackLat: c.lat + 0.003, fallbackLng: c.lng + 0.005, fallbackWalk: fallback.mrtMin },
      { key: 'hawker', icon: '🍜', color: '#f1c40f', label: amenities.hawker?.name || fallback.hawker || 'Hawker Centre', fallbackLat: c.lat - 0.003, fallbackLng: c.lng + 0.006, fallbackWalk: null },
      { key: 'park', icon: '🌳', color: '#27ae60', label: amenities.park?.name || fallback.park || 'Park', fallbackLat: c.lat + 0.007, fallbackLng: c.lng - 0.004, fallbackWalk: null },
      { key: 'school', icon: '🏫', color: '#9b59b6', label: amenities.school?.name || 'Primary School', fallbackLat: c.lat - 0.005, fallbackLng: c.lng - 0.006, fallbackWalk: null },
      { key: 'mall', icon: '🛍️', color: '#f39c12', label: amenities.mall?.name || 'Shopping Mall', fallbackLat: c.lat + 0.005, fallbackLng: c.lng + 0.004, fallbackWalk: null },
      { key: 'hospital', icon: '🏥', color: '#e74c3c', label: amenities.hospital?.name || 'Hospital', fallbackLat: c.lat + 0.002, fallbackLng: c.lng - 0.005, fallbackWalk: null },
    ];

    amenityDefs.forEach(def => {
      const d = amenities[def.key] || { lat: def.fallbackLat, lng: def.fallbackLng, name: def.label, walk_mins: def.fallbackWalk };
      if (!d || !d.lat || !d.lng) return;
      const displayName = d.name || def.label;
      const icon = L.divIcon({
        html: `<div style="background:${def.color};color:#fff;border-radius:8px;padding:3px 7px;font-size:11px;font-family:'DM Sans',sans-serif;font-weight:600;border:2px solid #0f0f0f;box-shadow:0 2px 8px rgba(0,0,0,.7);white-space:nowrap;display:flex;align-items:center;gap:4px">${def.icon} ${displayName}${d.walk_mins ? ' · ' + d.walk_mins + 'm' : ''}</div>`,
        className: '', iconAnchor: [0, 0],
      });
      const m = L.marker([d.lat, d.lng], { icon }).addTo(map);
      const line = L.polyline(
        [[c.lat, c.lng], [d.lat, d.lng]],
        { color: def.color, weight: 1.5, dashArray: '4 4', opacity: 0.6 }
      ).addTo(map);
      amenityMarkersRef.current.push(m, line);
    });
  }, [map, clearAmenityMarkers, recs]);

  // Build markers when recs change
  useEffect(() => {
    markersRef.current.forEach(m => map.removeLayer(m));
    clearAmenityMarkers();
    clearSharedAmenityMarkers();
    markersRef.current = [];
    townMarkersRef.current = {};

    const scoreByTown = {};
    recs.forEach(rec => { scoreByTown[rec.town] = rec; });

    ALL_TOWNS.forEach(town => {
      const rec = scoreByTown[town];
      const c = rec?.centroid || COORDS[town];
      if (!c) return;

      const s = rec ? rec.sc.total : null;
      const col = s !== null ? scoreToColor(s) : '#3d3d3d';
      const rank = rec ? recs.indexOf(rec) + 1 : null;
      const size = s !== null ? 34 : 24;

      const icon = L.divIcon({
        html: `<div style="background:${col};color:${s !== null ? '#fff' : '#888'};border-radius:50%;width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:${rank ? '11px' : '9px'};border:2px solid ${s !== null ? '#0f0f0f' : '#2c2c2c'};box-shadow:${s !== null ? '0 2px 10px rgba(0,0,0,.7)' : 'none'};font-family:'JetBrains Mono',monospace;opacity:${s !== null ? 1 : 0.5};transition:all .2s">${rank || '·'}</div>`,
        className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
      });

      const am = rec?.amenities || AMENITIES[town] || {};
      const amenityFallback = {
        mrt: 'MRT Station',
        hawker: 'Hawker Centre',
        park: 'Park',
        school: 'Primary School',
        mall: 'Shopping Mall',
        hospital: 'Hospital',
      };
      const amenityRow = (key, emoji) => {
        const item = am[key] || {};
        const name = item.name || amenityFallback[key] || key;
        const mins = item.walk_mins || item.mins || '-';
        return `<div style="font-size:.72rem;color:#aaa;margin-bottom:2px">${emoji} ${name} — ${mins} min walk</div>`;
      };

      let popupHtml;
      if (rec) {
        const tr = rec.pd.trend12;
        popupHtml = `
          <div style="font-size:.9rem;font-weight:600;margin-bottom:3px">#${rank} ${town}</div>
          <div style="font-size:.72rem;color:#888;margin-bottom:8px">${rec.ftype} · Score: <strong style="color:${col}">${s}/100</strong></div>
          <div style="display:flex;gap:10px;margin-bottom:6px">
            <div><div style="font-size:.62rem;color:#666;text-transform:uppercase;letter-spacing:.8px">Price Range</div>
              <div style="font-family:'JetBrains Mono',monospace;font-size:.82rem;color:#d4a843">$${(rec.pd.p25 / 1000).toFixed(0)}k–$${(rec.pd.p75 / 1000).toFixed(0)}k</div></div>
            <div><div style="font-size:.62rem;color:#666;text-transform:uppercase;letter-spacing:.8px">Median</div>
              <div style="font-family:'JetBrains Mono',monospace;font-size:.82rem">$${rec.pd.median.toLocaleString()}</div></div>
            <div><div style="font-size:.62rem;color:#666;text-transform:uppercase;letter-spacing:.8px">12-mo</div>
              <div style="font-family:'JetBrains Mono',monospace;font-size:.82rem;color:${tr > 0 ? '#e67e22' : '#27ae60'}">${tr > 0 ? '▲' : '▼'}${Math.abs(tr)}%</div></div>
          </div>
          ${amenityRow('mrt','🚇')}
          ${amenityRow('hawker','🍜')}
          ${amenityRow('park','🌳')}
          ${amenityRow('school','🏫')}
          ${amenityRow('mall','🛍️')}
          ${amenityRow('hospital','🏥')}
          <div style="font-size:.6rem;color:#444;margin-top:4px;border-top:1px solid #2c2c2c;padding-top:4px">
            Score breakdown: Budget ${rec.sc.budget.pts}/20 · Amenities ${rec.sc.amenity.pts}/30 · Transport ${rec.sc.transport.pts}/20 · Region ${rec.sc.region.pts}/15 · Flat ${rec.sc.flat.pts}/15
          </div>`;
      } else {
        popupHtml = `
          <div style="font-size:.88rem;font-weight:600;margin-bottom:3px">${town}</div>
          <div style="font-size:.72rem;color:#666">No data for your current filters.<br>Try adjusting flat type or budget.</div>`;
      }

      const m = L.marker([c.lat, c.lng], { icon });
      m.bindPopup(popupHtml, { maxWidth: 280 });
      m.addTo(map);
      markersRef.current.push(m);
      townMarkersRef.current[town] = m;
    });

    const resultCoords = recs
      .map(r => r.centroid || COORDS[r.town])
      .filter(c => c && c.lat && c.lng);
    if (resultCoords.length) {
      const bounds = L.latLngBounds(resultCoords.map(c => [c.lat, c.lng]));
      map.fitBounds(bounds.pad(0.25));
    }

    // Add amenity markers for all recommended towns (top 10 recs)
    recs.forEach(rec => {
      const c = rec.centroid || COORDS[rec.town];
      if (!c) return;
      const amenities = rec.amenities || {};
      const fallback = AMENITIES[rec.town] || {};
      const fallbackAmenity = {
        mrt: { lat: c.lat + 0.003, lng: c.lng + 0.005, name: fallback.mrt, walk_mins: fallback.mrtMin },
        hawker: { lat: c.lat - 0.003, lng: c.lng + 0.006, name: fallback.hawker, walk_mins: null },
        park: { lat: c.lat + 0.007, lng: c.lng - 0.004, name: fallback.park, walk_mins: null },
        school: { lat: c.lat - 0.005, lng: c.lng - 0.006, name: 'Primary School', walk_mins: null },
        mall: { lat: c.lat + 0.005, lng: c.lng + 0.004, name: 'Shopping Mall', walk_mins: null },
        hospital: { lat: c.lat + 0.002, lng: c.lng - 0.005, name: 'Hospital', walk_mins: null },
      };
      [
        { key: 'mrt', icon: '🚇', color: '#3498db' },
        { key: 'hawker', icon: '🍜', color: '#e67e22' },
        { key: 'park', icon: '🌳', color: '#27ae60' },
        { key: 'school', icon: '🏫', color: '#9b59b6' },
        { key: 'mall', icon: '🛍️', color: '#f39c12' },
        { key: 'hospital', icon: '🏥', color: '#9b59b6' },
      ].forEach(def => {
        const d = amenities[def.key] || fallbackAmenity[def.key];
        if (!d || !d.lat || !d.lng) return;
        const marker = L.circleMarker([d.lat, d.lng], {
          radius: 5,
          color: def.color,
          fillColor: def.color,
          fillOpacity: 0.9,
        }).addTo(map);
        marker.bindPopup(`<strong>${rec.town} ${def.key}</strong><br>${d.name || def.key} · ${d.walk_mins || '-'} min walk`);
        sharedAmenityMarkersRef.current.push(marker);

        const line = L.polyline(
          [[c.lat, c.lng], [d.lat, d.lng]],
          { color: def.color, weight: 1.2, dashArray: '3 3', opacity: 0.5 }
        ).addTo(map);
        sharedAmenityMarkersRef.current.push(line);
      });
    });
  }, [recs, map, clearAmenityMarkers, clearSharedAmenityMarkers]);

  // Handle highlighted town changes
  useEffect(() => {
    if (highlightedTown && townMarkersRef.current[highlightedTown]) {
      const marker = townMarkersRef.current[highlightedTown];
      marker.openPopup();
      map.setView(marker.getLatLng(), 14);
      showAmenityMarkers(highlightedTown);
    }
  }, [highlightedTown, map, showAmenityMarkers]);

  return null;
}

export default function MapView({ recs, highlightedTown }) {
  return (
    <div className="h-[calc(100vh-56px)] relative">
      <MapContainer
        center={[1.3521, 103.8198]}
        zoom={11}
        className="h-full w-full"
        zoomControl={true}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution="© OpenStreetMap © CartoDB"
          subdomains="abcd"
          maxZoom={19}
        />
        <MapContent recs={recs} highlightedTown={highlightedTown} />
      </MapContainer>
      {/* Legend */}
      <div className="absolute bottom-5 right-5 bg-dk2 border border-dk3 rounded-lg p-3 px-4 z-[900] text-[0.72rem] text-muted pointer-events-none min-w-[160px]">
        <div className="font-serif text-[0.88rem] text-white mb-2">Estate Score</div>
        <div className="h-2.5 rounded-[5px] bg-gradient-to-r from-[#c0392b] via-[#e67e22] via-50% via-[#f1c40f] to-[#27ae60] mb-1" />
        <div className="flex justify-between text-[0.62rem] text-muted">
          <span>0 Low</span><span>50</span><span>100 High</span>
        </div>
        <div className="mt-2.5 pt-2 border-t border-dk4">
          <div className="text-[0.68rem] text-light mb-1.5 font-medium">Amenities Shown</div>
          {[
            ['#3498db', 'MRT Station'],
            ['#f1c40f', 'Hawker Centre'],
            ['#27ae60', 'Park'],
            ['#9b59b6', 'School'],
            ['#f39c12', 'Mall'],
            ['#e74c3c', 'Hospital'],
          ].map(([color, label]) => (
            <div key={label} className="flex items-center gap-1.5 mb-1 text-[0.68rem]">
              <div className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
              {label}
            </div>
          ))}
          <div className="text-[0.6rem] text-muted mt-1">Click a card to show amenities</div>
        </div>
        <div className="text-[0.6rem] text-muted mt-2">All estates shown · color = score</div>
      </div>
    </div>
  );
}
