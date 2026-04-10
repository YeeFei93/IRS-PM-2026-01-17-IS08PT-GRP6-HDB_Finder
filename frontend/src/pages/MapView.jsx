import { useEffect, useRef, useCallback, useState } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import { ALL_TOWNS, COORDS, AMENITIES } from '../constants';
import { scoreToColor } from '../engine';
import { runFlatLookup } from '../api';

function MapContent({ recs, highlightedTown, onTownClick }) {
  const map = useMap();
  const markersRef = useRef([]);
  const amenityMarkersRef = useRef([]);
  const townMarkersRef = useRef({});

  // Use a ref so marker click always calls the latest onTownClick without
  // causing the build-markers effect to re-run on every render.
  const onTownClickRef = useRef(onTownClick);
  useEffect(() => { onTownClickRef.current = onTownClick; }, [onTownClick]);

  const clearAmenityMarkers = useCallback(() => {
    amenityMarkersRef.current.forEach(m => map.removeLayer(m));
    amenityMarkersRef.current = [];
  }, [map]);

  const showAmenityMarkers = useCallback((town) => {
    clearAmenityMarkers();
    const c = COORDS[town];
    const am = AMENITIES[town];
    if (!c || !am) return;

    const amenityDefs = [
      { icon: '🚇', color: '#3498db', label: am.mrt, mins: am.mrtMin, lat: c.lat + 0.003, lng: c.lng + 0.005 },
      { icon: '🍜', color: '#e67e22', label: am.hawker, lat: c.lat - 0.003, lng: c.lng + 0.006 },
      { icon: '🌳', color: '#27ae60', label: am.park, lat: c.lat + 0.007, lng: c.lng - 0.004 },
      { icon: '🏫', color: '#9b59b6', label: 'Primary School', lat: c.lat - 0.005, lng: c.lng - 0.006 },
    ];

    amenityDefs.forEach(def => {
      if (!def.label) return;
      const icon = L.divIcon({
        html: `<div style="background:${def.color};color:#fff;border-radius:8px;padding:3px 7px;font-size:11px;font-family:'DM Sans',sans-serif;font-weight:600;border:2px solid #0f0f0f;box-shadow:0 2px 8px rgba(0,0,0,.7);white-space:nowrap;display:flex;align-items:center;gap:4px">${def.icon} ${def.label}${def.mins ? ' · ' + def.mins + 'm' : ''}</div>`,
        className: '', iconAnchor: [0, 0],
      });
      const m = L.marker([def.lat, def.lng], { icon }).addTo(map);
      const line = L.polyline(
        [[c.lat, c.lng], [def.lat, def.lng]],
        { color: def.color, weight: 1.5, dashArray: '4 4', opacity: 0.6 }
      ).addTo(map);
      amenityMarkersRef.current.push(m, line);
    });
  }, [map, clearAmenityMarkers]);

  // Build markers when recs change
  useEffect(() => {
    markersRef.current.forEach(m => map.removeLayer(m));
    clearAmenityMarkers();
    markersRef.current = [];
    townMarkersRef.current = {};

    const scoreByTown = {};
    recs.forEach(rec => { scoreByTown[rec.town] = rec; });

    ALL_TOWNS.forEach(town => {
      const c = COORDS[town];
      if (!c) return;

      const rec = scoreByTown[town];
      const s = rec ? rec.sc.total : null;
      const col = s !== null ? scoreToColor(s) : '#3d3d3d';
      const rank = rec ? recs.indexOf(rec) + 1 : null;
      const size = s !== null ? 34 : 24;

      const icon = L.divIcon({
        html: `<div style="background:${col};color:${s !== null ? '#fff' : '#888'};border-radius:50%;width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:${rank ? '11px' : '9px'};border:2px solid ${s !== null ? '#0f0f0f' : '#2c2c2c'};box-shadow:${s !== null ? '0 2px 10px rgba(0,0,0,.7)' : 'none'};font-family:'JetBrains Mono',monospace;opacity:${s !== null ? 1 : 0.5};transition:all .2s">${rank || '·'}</div>`,
        className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2],
      });

      const am = AMENITIES[town] || {};
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
          ${am.mrt ? `<div style="font-size:.72rem;color:#aaa;margin-bottom:2px">🚇 ${am.mrt} — ${am.mrtMin} min walk</div>` : ''}
          ${am.hawker ? `<div style="font-size:.72rem;color:#aaa;margin-bottom:2px">🍜 ${am.hawker}</div>` : ''}
          ${am.park ? `<div style="font-size:.72rem;color:#aaa;margin-bottom:4px">🌳 ${am.park}</div>` : ''}
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
      m.on('click', () => onTownClickRef.current(town));
      m.addTo(map);
      markersRef.current.push(m);
      townMarkersRef.current[town] = m;
    });

    const resultCoords = recs.filter(r => COORDS[r.town]).map(r => COORDS[r.town]);
    if (resultCoords.length) {
      const bounds = L.latLngBounds(resultCoords.map(c => [c.lat, c.lng]));
      map.fitBounds(bounds.pad(0.25));
    }
  }, [recs, map, clearAmenityMarkers]);

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

export default function MapView({ recs, highlightedTown, formState, effectiveBudget }) {
  const [drillTown, setDrillTown] = useState(null);
  const [drillFlats, setDrillFlats] = useState([]);
  const [drillLoading, setDrillLoading] = useState(false);
  const [drillError, setDrillError] = useState(null);

  const handleTownClick = useCallback(async (town) => {
    setDrillTown(town);
    setDrillFlats([]);
    setDrillError(null);
    setDrillLoading(true);
    try {
      const result = await runFlatLookup({
        estate:     town,
        ftype:      formState?.ftype,
        floor_pref: formState?.floor,
        budget:     effectiveBudget,
        min_lease:  formState?.lease,
      });
      // Express wraps Python result: { status, result: { estate, flats } }
      const data = result.result ?? result;
      setDrillFlats(data.flats || []);
    } catch (e) {
      setDrillError(e.message);
    } finally {
      setDrillLoading(false);
    }
  }, [formState, effectiveBudget]);

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
        <MapContent recs={recs} highlightedTown={highlightedTown} onTownClick={handleTownClick} />
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
            ['#e67e22', 'Hawker Centre'],
            ['#27ae60', 'Park'],
            ['#9b59b6', 'School'],
          ].map(([color, label]) => (
            <div key={label} className="flex items-center gap-1.5 mb-1 text-[0.68rem]">
              <div className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
              {label}
            </div>
          ))}
          <div className="text-[0.6rem] text-muted mt-1">Click a marker to view listings</div>
        </div>
        <div className="text-[0.6rem] text-muted mt-2">All estates shown · color = score</div>
      </div>

      {/* Drill-down panel */}
      {drillTown && (
        <div style={{
          position: 'absolute', right: 0, top: 0, bottom: 0,
          width: '340px', background: '#111', borderLeft: '1px solid #2a2a2a',
          zIndex: 1000, display: 'flex', flexDirection: 'column',
          fontFamily: "'DM Sans', sans-serif",
        }}>
          {/* Panel header */}
          <div style={{ padding: '14px 16px', borderBottom: '1px solid #2a2a2a', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <div>
              <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#e0e0e0' }}>{drillTown}</div>
              <div style={{ fontSize: '0.72rem', color: '#555', marginTop: 3 }}>
                {formState?.ftype || 'Any type'} · Sorted by price proximity to your budget
              </div>
            </div>
            <button
              onClick={() => setDrillTown(null)}
              style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', fontSize: '1.1rem', padding: '2px 4px', lineHeight: 1 }}
            >✕</button>
          </div>

          {/* Panel body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px' }}>
            {drillLoading && (
              <div style={{ textAlign: 'center', paddingTop: 48, color: '#444', fontSize: '0.8rem' }}>
                Loading listings…
              </div>
            )}
            {drillError && (
              <div style={{ color: '#c0392b', padding: '16px 8px', fontSize: '0.78rem' }}>
                {drillError}
              </div>
            )}
            {!drillLoading && !drillError && drillFlats.length === 0 && (
              <div style={{ textAlign: 'center', paddingTop: 48, color: '#444', fontSize: '0.8rem' }}>
                No listings found for your current filters.
              </div>
            )}
            {drillFlats.map((flat, i) => {
              const over = effectiveBudget && flat.resale_price > effectiveBudget;
              const pct = effectiveBudget ? Math.abs(flat.resale_price - effectiveBudget) / effectiveBudget : 1;
              const nearBudget = pct <= 0.05;
              return (
                <div key={i} style={{
                  background: nearBudget ? '#192419' : '#181818',
                  border: `1px solid ${nearBudget ? '#2a4a2a' : '#242424'}`,
                  borderRadius: 8,
                  padding: '10px 12px',
                  marginBottom: 8,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#d0d0d0', lineHeight: 1.3 }}>
                      Blk {flat.block} {flat.street_name}
                    </div>
                    <div style={{ fontSize: '0.78rem', fontFamily: "'JetBrains Mono', monospace", color: over ? '#e67e22' : '#27ae60', fontWeight: 700, whiteSpace: 'nowrap' }}>
                      ${flat.resale_price.toLocaleString()}
                    </div>
                  </div>
                  <div style={{ marginTop: 5, display: 'flex', gap: 6, flexWrap: 'wrap', fontSize: '0.67rem', color: '#555' }}>
                    <span>Floor&nbsp;{flat.storey_range_start}–{flat.storey_range_end}</span>
                    <span>·</span>
                    <span>{flat.floor_area_sqm}&nbsp;sqm</span>
                    <span>·</span>
                    <span>Lease&nbsp;{flat.remaining_lease_years}y{flat.remaining_lease_months > 0 ? ` ${flat.remaining_lease_months}m` : ''}</span>
                  </div>
                  <div style={{ marginTop: 4, fontSize: '0.64rem', color: '#3a3a3a', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>Sold {flat.sold_date}</span>
                    {nearBudget && <span style={{ color: '#27ae60', fontWeight: 700 }}>✓ Near budget</span>}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Panel footer */}
          {!drillLoading && drillFlats.length > 0 && (
            <div style={{ padding: '8px 16px', borderTop: '1px solid #242424', fontSize: '0.65rem', color: '#3a3a3a' }}>
              {drillFlats.length} recent transactions shown
            </div>
          )}
        </div>
      )}
    </div>
  );
}
