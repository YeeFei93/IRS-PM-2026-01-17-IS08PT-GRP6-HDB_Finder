import { useEffect, useRef, useCallback, useState } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import { ALL_TOWNS, COORDS, AMENITIES } from '../constants';
import { scoreToColor, whyText } from '../engine';
import { runFlatLookup, runFlatAmenities } from '../api';

// Ray-casting point-in-polygon for GeoJSON ring coordinates [lng, lat]
function pointInPolygon(lat, lng, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1];
    const xj = ring[j][0], yj = ring[j][1];
    if ((yi > lat) !== (yj > lat) && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

// Returns true if [lat, lng] is inside any ring of a GeoJSON Polygon/MultiPolygon geometry
function pointInGeoJsonGeometry(lat, lng, geometry) {
  if (!geometry) return true; // no data, don't filter
  const polys = geometry.type === 'MultiPolygon'
    ? geometry.coordinates.map(p => p[0])
    : [geometry.coordinates[0]];
  return polys.some(ring => pointInPolygon(lat, lng, ring));
}

function MapContent({ recs, highlightedTown, onTownClick, mapRef, drillFlats, activeFlatEstate, onEstateSelect, effectiveBudget, flyToFlatRef, selectedEstate, hoveredFlatIdx, selectedFlat, onFilteredFlats }) {
  const map = useMap();
  const geoLayersRef = useRef([]);       // for mass-removal on recs change
  const geoLayerByTownRef = useRef({}); // town -> { layer, baseStyle }
  const labelMarkersRef = useRef([]); // town-name label markers
  const amenityMarkersRef = useRef([]);
  const flatMarkersRef = useRef([]);
  const estateMarkersRef = useRef([]);  // numbered gold markers for top-5 estates
  const amenityMarkersPhase3Ref = useRef([]);  // park markers for the selected flat
  const geoDataRef = useRef(null);    // cached GeoJSON
  const drillFlatsRef = useRef([]);   // always-current drillFlats for use inside renderGeo
  const activeFlatEstateRef = useRef(null);
  const selectedEstateRef = useRef(null);
  const selectedFlatRef = useRef(null);
  const flatListRef = useRef([]);     // flat list mirroring flatMarkersRef order

  // Expose map instance for external fly-to calls
  useEffect(() => { mapRef.current = map; }, [map, mapRef]);
  useEffect(() => { drillFlatsRef.current = drillFlats; }, [drillFlats]);
  useEffect(() => { activeFlatEstateRef.current = activeFlatEstate; }, [activeFlatEstate]);
  useEffect(() => { selectedEstateRef.current = selectedEstate; }, [selectedEstate]);
  useEffect(() => { selectedFlatRef.current = selectedFlat; }, [selectedFlat]);

  const onTownClickRef = useRef(onTownClick);
  useEffect(() => { onTownClickRef.current = onTownClick; }, [onTownClick]);

  const onEstateSelectRef = useRef(onEstateSelect);
  useEffect(() => { onEstateSelectRef.current = onEstateSelect; }, [onEstateSelect]);

  const recsRef = useRef(recs);
  useEffect(() => { recsRef.current = recs; }, [recs]);

  const clearFlatAmenityMarkers = useCallback(() => {
    amenityMarkersPhase3Ref.current.forEach(m => map.removeLayer(m));
    amenityMarkersPhase3Ref.current = [];
  }, [map]);

  // Config for each amenity type shown in Phase 3
  const FLAT_AMENITY_CFG = {
    parks:     { color: '#27ae60', emoji: '🌳', label: 'Park',      threshold: '1km' },
    hawkers:   { color: '#e67e22', emoji: '🍜', label: 'Hawker',    threshold: '1km' },
    mrts:      { color: '#3498db', emoji: '🚇', label: 'MRT',       threshold: '1km' },
    schools:   { color: '#9b59b6', emoji: '📚', label: 'School',    threshold: '1km' },
    malls:     { color: '#f3e412', emoji: '🛍️', label: 'Mall',      threshold: '1.5km' },
    hospitals: { color: '#e74c3c', emoji: '🏥', label: 'Hospital',  threshold: '3km' },
  };

  const showFlatAmenityMarkers = useCallback((amenities, flatLat, flatLng) => {
    clearFlatAmenityMarkers();
    // amenities may be the old { parks: [...] } shape or a flat array (legacy)
    const byType = Array.isArray(amenities)
      ? { parks: amenities }
      : amenities;

    Object.entries(byType).forEach(([type, items]) => {
      if (!items?.length) return;
      const cfg = FLAT_AMENITY_CFG[type] || { color: '#888', emoji: '📍', label: type };
      items.forEach(item => {
        // support legacy park_name key; for hawkers show only the text inside () if present
        const rawName = item.name || item.park_name || '';
        const parenMatch = type === 'hawkers' && rawName.match(/\(([^)]+)\)/);
        const name = parenMatch ? parenMatch[1] : rawName;
        const icon = L.divIcon({
          html: `<div style="background:${cfg.color};color:#fff;border-radius:8px;padding:3px 7px;font-size:10px;font-family:'DM Sans',sans-serif;font-weight:600;border:2px solid #0f0f0f;box-shadow:0 2px 8px rgba(0,0,0,.7);white-space:nowrap">${cfg.emoji} ${name} · ${item.distance.toFixed(2)}km</div>`,
          className: '', iconAnchor: [0, 0],
        });
        const m = L.marker([item.latitude, item.longitude], { icon }).addTo(map);
        const line = L.polyline(
          [[flatLat, flatLng], [item.latitude, item.longitude]],
          { color: cfg.color, weight: 1.5, dashArray: '4 4', opacity: 0.6 }
        ).addTo(map);
        amenityMarkersPhase3Ref.current.push(m, line);
      });
    });
  }, [map, clearFlatAmenityMarkers]);

  // Expose showParkMarkers and clearParkMarkers for external use
  const showAmenityMarkersRef = useRef(showFlatAmenityMarkers);
  const clearAmenityMarkersRef = useRef(clearFlatAmenityMarkers);
  useEffect(() => { showAmenityMarkersRef.current = showFlatAmenityMarkers; }, [showFlatAmenityMarkers]);
  useEffect(() => { clearAmenityMarkersRef.current = clearFlatAmenityMarkers; }, [clearFlatAmenityMarkers]);

  const flyToFlat = useCallback((flat) => {
    if (!flat.latitude || !flat.longitude) return;
    // Fit a tiny bbox centred on the pin, with right padding for the panel
    // so the pin lands at the centroid of visible map space
    const zoom = 16;
    const pad = 0.003; // ~330m — enough to show nearby parks
    map.flyToBounds(
      [[flat.latitude - pad, flat.longitude - pad], [flat.latitude + pad, flat.longitude + pad]],
      { paddingBottomRight: [340, 40], paddingTopLeft: [40, 40], maxZoom: zoom, animate: true, duration: 0.7 }
    );
    clearAmenityMarkersRef.current();
    runFlatAmenities(flat.block, flat.street_name)
      .then(res => {
        const data = res.result ?? res;
        // data contains { parks, hawkers, mrts, schools, malls, hospitals }
        const { block: _b, street_name: _s, ...amenities } = data;
        const hasAny = Object.values(amenities).some(arr => arr?.length);
        if (hasAny) showAmenityMarkersRef.current(amenities, flat.latitude, flat.longitude);
      })
      .catch(() => {});
  }, [map]);
  useEffect(() => { if (flyToFlatRef) flyToFlatRef.current = flyToFlat; }, [flyToFlat, flyToFlatRef]);

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
      { icon: '🚇', color: '#3498db', label: am.mrt,    mins: am.mrtMin, lat: c.lat + 0.003, lng: c.lng + 0.005 },
      { icon: '🍜', color: '#e67e22', label: am.hawker,              lat: c.lat - 0.003, lng: c.lng + 0.006 },
      { icon: '🌳', color: '#27ae60', label: am.park,                lat: c.lat + 0.007, lng: c.lng - 0.004 },
      { icon: '🏫', color: '#9b59b6', label: 'Primary School',       lat: c.lat - 0.005, lng: c.lng - 0.006 },
      { icon: '🛍️', color: '#f39c12', label: am.mall,                lat: c.lat + 0.005, lng: c.lng - 0.007 },
      { icon: '🏥', color: '#e74c3c', label: am.hospital,            lat: c.lat - 0.007, lng: c.lng + 0.003 },
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

  // Build polygon fills when recs change
  useEffect(() => {
    // Clear previous layers and labels
    geoLayersRef.current.forEach(l => map.removeLayer(l));
    labelMarkersRef.current.forEach(l => map.removeLayer(l));
    clearAmenityMarkers();
    geoLayersRef.current = [];
    labelMarkersRef.current = [];
    geoLayerByTownRef.current = {};

    const scoreByTown = {};
    recs.forEach(rec => { scoreByTown[rec.town] = rec; });

    const renderGeo = (geoData) => {
      geoData.features.forEach(feat => {
        const town = feat.properties.estate;
        const rec = scoreByTown[town];
        const s = rec ? rec.sc.total : null;
        const col = s !== null ? scoreToColor(s) : '#3d3d3d';
        const rank = rec ? recs.indexOf(rec) + 1 : null;

        const baseStyle = {
          fillColor: '#3d3d3d',
          fillOpacity: s !== null ? 0.15 : 0.08,
          color: '#444',
          weight: s !== null ? 1.0 : 0.6,
          opacity: s !== null ? 0.5 : 0.3,
        };
        const layer = L.geoJSON(feat, { style: baseStyle, interactive: true });

        const am = AMENITIES[town] || {};
        let popupHtml;
        if (rec) {
          const tr = rec.pd.trend12;
          popupHtml = `
            <div style="font-size:.9rem;font-weight:600;margin-bottom:3px">#${rank} ${town}</div>
            <div style="font-size:.72rem;color:#888;margin-bottom:8px">${rec.ftype} · Score: <strong style="color:${col}">${s}/100</strong></div>
            <div style="display:flex;gap:10px;margin-bottom:6px">
              <div><div style="font-size:.62rem;color:#666;text-transform:uppercase;letter-spacing:.8px">Price Range</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:.82rem;color:#d4a843">$${(rec.pd.p25/1000).toFixed(0)}k–$${(rec.pd.p75/1000).toFixed(0)}k</div></div>
              <div><div style="font-size:.62rem;color:#666;text-transform:uppercase;letter-spacing:.8px">Median</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:.82rem">$${rec.pd.median.toLocaleString()}</div></div>
              <div><div style="font-size:.62rem;color:#666;text-transform:uppercase;letter-spacing:.8px">12-mo</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:.82rem;color:${tr > 0 ? '#e67e22' : '#27ae60'}">${tr > 0 ? '▲' : '▼'}${Math.abs(tr)}%</div></div>
            </div>
            ${am.mrt ? `<div style="font-size:.72rem;color:#aaa;margin-bottom:2px">🚇 ${am.mrt} — ${am.mrtMin} min walk</div>` : ''}
            ${am.hawker ? `<div style="font-size:.72rem;color:#aaa;margin-bottom:2px">🍜 ${am.hawker}</div>` : ''}
            ${am.park ? `<div style="font-size:.72rem;color:#aaa;margin-bottom:4px">🌳 ${am.park}</div>` : ''}
            <div style="font-size:.6rem;color:#444;margin-top:4px;border-top:1px solid #2c2c2c;padding-top:4px">
              Budget ${rec.sc.budget.pts}/20 · Amenities ${rec.sc.amenity.pts}/30 · Transport ${rec.sc.transport.pts}/20 · Region ${rec.sc.region.pts}/15 · Flat ${rec.sc.flat.pts}/15
            </div>`;
        } else {
          popupHtml = `
            <div style="font-size:.88rem;font-weight:600;margin-bottom:3px">${town}</div>
            <div style="font-size:.72rem;color:#666">No data for your current filters.<br>Try adjusting flat type or budget.</div>`;
        }

        layer.bindPopup(popupHtml, { maxWidth: 280 });
        // Initial click/hover — will be overridden by hot-estate effect when drillFlats load
        layer.on('click', () => onTownClickRef.current(town));
        layer.on('mouseover', () => layer.setStyle({ fillOpacity: Math.min(baseStyle.fillOpacity + 0.2, 0.9) }));
        layer.on('mouseout', () => layer.setStyle(baseStyle));
        layer.addTo(map);
        geoLayersRef.current.push(layer);
        geoLayerByTownRef.current[town] = { layer, baseStyle };
      });

      // Re-apply hot-estate styling immediately after rebuild so gold persists
      applyHotStyleRef.current();
    };

    if (geoDataRef.current) {
      renderGeo(geoDataRef.current);
    } else {
      fetch('/estates.geojson')
        .then(r => r.json())
        .then(data => { geoDataRef.current = data; renderGeo(data); });
    }
  }, [recs, map, clearAmenityMarkers]);

  // Handle highlighted town — open popup and show amenities
  useEffect(() => {
    if (!highlightedTown) return;
    const c = COORDS[highlightedTown];
    if (c) {
      map.setView([c.lat, c.lng], 14);
      showAmenityMarkers(highlightedTown);
    }
  }, [highlightedTown, map, showAmenityMarkers]);

  // Re-style estate polygons: gold for hot estates (have top flats), dimmed for others
  const applyHotStyle = useCallback(() => {
    const activeEstate = activeFlatEstateRef.current;
    const selEstate = selectedEstateRef.current;
    // Phase 1: top-5 gold (selected = brighter). Phase 2: active estate only.
    const hot = activeEstate
      ? new Set([activeEstate])
      : new Set(recsRef.current.slice(0, 5).map(r => r.town));
    Object.entries(geoLayerByTownRef.current).forEach(([town, { layer, baseStyle }]) => {
      layer.off('click');
      layer.off('mouseover');
      layer.off('mouseout');
      if (hot.size === 0) {
        layer.setStyle(baseStyle);
        layer.on('click', () => onTownClickRef.current(town));
        layer.on('mouseover', () => layer.setStyle({ ...baseStyle, fillOpacity: Math.min(baseStyle.fillOpacity + 0.2, 0.9) }));
        layer.on('mouseout', () => layer.setStyle(baseStyle));
      } else if (hot.has(town)) {
        const isActive = town === activeEstate;
        const isSelected = !activeEstate && town === selEstate;
        const inPhase3 = !!selectedFlatRef.current;
        const fillOp = isActive ? (inPhase3 ? 0.12 : 0.65) : isSelected ? 0.55 : 0.32;
        const w = isActive || isSelected ? 2.5 : 1.8;
        const hotStyle = { fillColor: '#27ae60', fillOpacity: fillOp, color: '#27ae60', weight: w, opacity: 1 };
        layer.setStyle(hotStyle);
        layer.on('mouseover', () => layer.setStyle({ ...hotStyle, fillOpacity: Math.min(fillOp + 0.2, 0.85) }));
        layer.on('mouseout', () => layer.setStyle(hotStyle));
        layer.on('click', () => onEstateSelectRef.current(town));
      } else {
        layer.setStyle({ ...baseStyle, fillOpacity: 0.05, opacity: 0.1, weight: 0.4 });
      }
    });
  }, []);
  const applyHotStyleRef = useRef(applyHotStyle);
  useEffect(() => { applyHotStyleRef.current = applyHotStyle; }, [applyHotStyle]);

  useEffect(() => {
    applyHotStyle();

    // In overview mode (no active estate), fit map to top-5 recommended estates
    const hotTowns = activeFlatEstate ? [activeFlatEstate] : recs.slice(0, 5).map(r => r.town);
    if (hotTowns.length > 0 && !activeFlatEstate) {
      const bounds = L.latLngBounds();
      hotTowns.forEach(town => {
        const entry = geoLayerByTownRef.current[town];
        if (entry) {
          try { bounds.extend(entry.layer.getBounds()); } catch {}
        } else if (COORDS[town]) {
          bounds.extend([COORDS[town].lat, COORDS[town].lng]);
        }
      });
      if (bounds.isValid()) map.fitBounds(bounds.pad(0.1), { minZoom: 11, maxZoom: 13, paddingTopLeft: [0, 0], paddingBottomRight: [320, 100] });
    }
  }, [recs, activeFlatEstate, map]);

  // Re-style when a flat is selected/deselected (Phase 3 polygon dimming)
  useEffect(() => { applyHotStyleRef.current(); }, [selectedFlat]);

  // Icon factory for flat markers — supports hover/selected states
  const makeFlatIcon = useCallback((flat, rank, isHovered, isSelected, isDimmed) => {
    const pct = effectiveBudget ? Math.abs(flat.resale_price - effectiveBudget) / effectiveBudget : 1;
    const nearBudget = pct <= 0.05;
    const over = effectiveBudget && flat.resale_price > effectiveBudget;
    const col = nearBudget ? '#27ae60' : over ? '#c0392b' : '#d4a843';
    const size = isSelected ? 34 : isHovered ? 30 : 26;
    const border = isSelected ? '2px solid #fff' : '2px solid #0f0f0f';
    const opacity = isDimmed ? 0.25 : 1;
    return L.divIcon({
      html: `<div style="background:${col};color:#fff;border-radius:50%;width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:${isSelected?11:10}px;border:${border};box-shadow:0 ${isSelected?4:2}px ${isSelected?12:8}px rgba(0,0,0,.8);font-family:'JetBrains Mono',monospace;opacity:${opacity}">${rank}</div>`,
      className: '', iconSize: [size, size], iconAnchor: [size/2, size/2],
    });
  }, [effectiveBudget]);

  // Flat markers — Phase 2: shown when estate selected
  useEffect(() => {
    flatMarkersRef.current.forEach(m => map.removeLayer(m));
    flatMarkersRef.current = [];
    flatListRef.current = [];
    clearAmenityMarkers();
    clearFlatAmenityMarkers();

    if (!activeFlatEstate) { onFilteredFlats?.([]); return; }
    const flats = drillFlats.filter(f => f.latitude && f.longitude);
    onFilteredFlats?.(flats);
    if (!flats.length) return;

    flatListRef.current = flats;
    flats.forEach((flat, i) => {
      const pct = effectiveBudget ? Math.abs(flat.resale_price - effectiveBudget) / effectiveBudget : 1;
      const nearBudget = pct <= 0.05;
      const over = effectiveBudget && flat.resale_price > effectiveBudget;
      const col = nearBudget ? '#27ae60' : over ? '#c0392b' : '#d4a843';
      const icon = makeFlatIcon(flat, i + 1, false, false);
      const popupHtml = `
        <div style="font-size:.82rem;font-weight:600;margin-bottom:2px">Blk ${flat.block} ${flat.street_name}</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:.88rem;color:${col};font-weight:700;margin-bottom:4px">$${flat.resale_price.toLocaleString()}</div>
        <div style="font-size:.72rem;color:#aaa">${flat.flat_type} · ${flat.floor_area_sqm} sqm · Floor ${flat.storey_range_start}–${flat.storey_range_end} · Lease ${flat.remaining_lease_years}y</div>
        <div style="font-size:.68rem;color:#666;margin-top:2px">${flat.estate} · ${flat.sold_date}</div>`;
      const m = L.marker([flat.latitude, flat.longitude], { icon });
      m.bindPopup(popupHtml, { maxWidth: 260 });
      m.on('click', () => flyToFlat(flat));
      m.addTo(map);
      flatMarkersRef.current.push(m);
    });

    const estateLayer = geoLayerByTownRef.current[activeFlatEstate]?.layer;
    if (estateLayer) {
      try { map.fitBounds(estateLayer.getBounds().pad(0.15), { paddingBottomRight: [340, 0] }); } catch {}
    } else if (flats.length > 1) {
      map.fitBounds(L.latLngBounds(flats.map(f => [f.latitude, f.longitude])).pad(0.3));
    } else {
      map.setView([flats[0].latitude, flats[0].longitude], 15);
    }
  }, [activeFlatEstate, drillFlats, effectiveBudget, map, clearAmenityMarkers, clearFlatAmenityMarkers, flyToFlat, makeFlatIcon, onFilteredFlats]);

  // Phase 3: update flat marker icons on hover/selection without recreating them
  useEffect(() => {
    const anySelected = !!selectedFlat;
    flatListRef.current.forEach((flat, i) => {
      const marker = flatMarkersRef.current[i];
      if (!marker) return;
      const isHovered = hoveredFlatIdx === i;
      const isSelected = selectedFlat?._idx === i;
      const isDimmed = anySelected && !isSelected;
      marker.setIcon(makeFlatIcon(flat, i + 1, isHovered, isSelected, isDimmed));
      marker.setZIndexOffset(isSelected ? 2000 : isHovered ? 1000 : 0);
    });
  }, [hoveredFlatIdx, selectedFlat, makeFlatIcon]);

  // Phase 1: zoom to selectedEstate when estate card is clicked
  useEffect(() => {
    if (!selectedEstate || activeFlatEstate) return;
    applyHotStyleRef.current();
    const entry = geoLayerByTownRef.current[selectedEstate];
    if (entry) {
      try { map.fitBounds(entry.layer.getBounds().pad(0.2), { paddingBottomRight: [340, 0], maxZoom: 13 }); } catch {}
    } else {
      const c = COORDS[selectedEstate];
      if (c) map.flyTo([c.lat, c.lng], 13, { animate: true, duration: 0.5 });
    }
  }, [selectedEstate, activeFlatEstate, map]);

  // Estate markers — numbered gold pins on top-5 estates in overview mode
  useEffect(() => {
    estateMarkersRef.current.forEach(m => map.removeLayer(m));
    estateMarkersRef.current = [];
    if (activeFlatEstate) return; // Phase 2+: hide estate markers
    recs.slice(0, 5).forEach((rec, i) => {
      const c = COORDS[rec.town];
      if (!c) return;
      const isSel = rec.town === selectedEstate;
      const size = isSel ? 34 : 28;
      const icon = L.divIcon({
        html: `<div style="background:#27ae60;color:#fff;border-radius:50%;width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:${isSel?12:11}px;border:${isSel?'2px solid #fff':'2px solid #0f0f0f'};box-shadow:0 ${isSel?4:2}px ${isSel?12:8}px rgba(0,0,0,.8);font-family:'JetBrains Mono',monospace">${i + 1}</div>`,
        className: '', iconSize: [size, size], iconAnchor: [size/2, size/2],
      });
      const m = L.marker([c.lat, c.lng], { icon });
      m.on('click', () => onTownClickRef.current(rec.town));
      m.addTo(map);
      estateMarkersRef.current.push(m);
    });
  }, [recs, activeFlatEstate, selectedEstate, map]);

  return null;
}

export default function MapView({ recs, highlightedTown, formState, effectiveBudget, derived, rawCount, latestMonth }) {
  const [drillTown, setDrillTown] = useState(null);
  const [drillFlats, setDrillFlats] = useState([]);
  const [drillLoading, setDrillLoading] = useState(false);
  const [drillError, setDrillError] = useState(null);
  const [selectedEstate, setSelectedEstate] = useState(null);  // Phase 1: card highlight
  const [activeFlatEstate, setActiveFlatEstate] = useState(null); // Phase 2: flat view
  const [selectedFlat, setSelectedFlat] = useState(null);         // Phase 3: flat detail
  const [hoveredFlatIdx, setHoveredFlatIdx] = useState(null);
  const mapRef = useRef(null);
  const flyToFlatRef = useRef(null);
  const [filteredFlats, setFilteredFlats] = useState([]);
  const handleFilteredFlats = useCallback((flats) => setFilteredFlats(flats), []);

  const loadFlats = useCallback(async ({ estate, estates }) => {
    setDrillTown(estate || null);
    setDrillError(null);
    setDrillLoading(true);
    try {
      const payload = {
        ftype:      formState?.ftype,
        floor_pref: formState?.floor,
        budget:     effectiveBudget,
        min_lease:  formState?.lease,
        limit:      10,
      };
      if (estates) payload.estates = estates;
      else payload.estate = estate;

      const result = await runFlatLookup(payload);
      const data = result.result ?? result;
      setDrillFlats(data.flats || []);
    } catch (e) {
      setDrillFlats([]);
      setDrillError(e.message);
    } finally {
      setDrillLoading(false);
    }
  }, [formState, effectiveBudget]);

  const handleTownClick = useCallback((town) => {
    setSelectedEstate(town);
    setActiveFlatEstate(town);
    loadFlats({ estate: town });
  }, [loadFlats]);

  // Stable ref for auto-load effect
  const loadFlatsRef = useRef(loadFlats);
  useEffect(() => { loadFlatsRef.current = loadFlats; }, [loadFlats]);

  // Fly map to the estate whose flats are shown in the panel
  const flyToEstate = useCallback((town) => {
    const coords = COORDS[town];
    if (coords && mapRef.current) {
      mapRef.current.flyTo([coords.lat, coords.lng], 15, { animate: true, duration: 0.8 });
    }
  }, []);

  const zoomOut = useCallback(() => {
    setActiveFlatEstate(null);
    setSelectedEstate(null);
    setSelectedFlat(null);
    setHoveredFlatIdx(null);
    setDrillFlats([]);
    setFilteredFlats([]);
    // MapContent GeoJSON effect will fitBounds top-5 estates when activeFlatEstate clears
  }, []);

  // Reset to Phase 1 whenever a new search result arrives
  useEffect(() => {
    if (!recs.length) return;
    setActiveFlatEstate(null);
    setSelectedEstate(null);
    setSelectedFlat(null);
    setHoveredFlatIdx(null);
    setDrillFlats([]);
    setFilteredFlats([]);
    // Map zoom is handled by the MapContent GeoJSON effect which fitBounds top-5 estates
  }, [recs]);

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
        <MapContent recs={recs} highlightedTown={highlightedTown} onTownClick={handleTownClick} mapRef={mapRef} drillFlats={drillFlats} activeFlatEstate={activeFlatEstate} onEstateSelect={(town) => { setActiveFlatEstate(town); loadFlats({ estate: town }); }} effectiveBudget={effectiveBudget} flyToFlatRef={flyToFlatRef} selectedEstate={selectedEstate} hoveredFlatIdx={hoveredFlatIdx} selectedFlat={selectedFlat} onFilteredFlats={handleFilteredFlats} />
      </MapContainer>

      {/* Zoom-out button */}
      <button
        onClick={zoomOut}
        className="absolute top-3 left-3 z-[900] bg-dk2 border border-dk3 text-white text-xs px-3 py-1.5 rounded-lg hover:bg-dk3 transition-colors"
        title="Zoom out to overview"
      >
        ⊖ Overview
      </button>

      {/* Legend */}
      <div className="absolute bottom-5 left-5 bg-dk2 border border-dk3 rounded-lg p-3 px-4 z-[900] text-[0.72rem] text-muted pointer-events-none min-w-[160px]">
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
            ['#9b59b6', 'Pri School'],
            ['#f3e412', 'Mall'],
            ['#e74c3c', 'Hospital'],
          ].map(([color, label]) => (
            <div key={label} className="flex items-center gap-1.5 mb-1 text-[0.68rem]">
              <span style={{ color }}>{icon}</span>
              {label}
            </div>
          ))}
          <div className="text-[0.6rem] text-muted mt-1">Click a marker to view listings</div>
        </div>
        <div className="text-[0.6rem] text-muted mt-2">All estates shown · color = score</div>
      </div>

      {/* Results panel — always visible once recs arrive */}
      {recs.length > 0 && (
        <div style={{
          position: 'absolute', right: 0, top: 0, bottom: 0,
          width: '340px', background: '#111', borderLeft: '1px solid #2a2a2a',
          zIndex: 1000, display: 'flex', flexDirection: 'column',
          fontFamily: "'DM Sans', sans-serif",
        }}>
          {/* Header */}
          <div style={{ padding: '12px 14px 10px', borderBottom: '1px solid #2a2a2a' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: '0.95rem', color: '#e0e0e0' }}>
                  {activeFlatEstate
                    ? activeFlatEstate
                    : `Top ${Math.min(recs.length, 5)} Estates`}
                </div>
                <div style={{ fontSize: '0.68rem', color: '#555', marginTop: 2 }}>
                  {activeFlatEstate
                    ? `${formState?.ftype || ''} · hover card to highlight · click to zoom`
                    : `${formState?.ftype || 'Any type'} · cosine similarity · ${recs[0]?.sc?.active?.length || 0} criteria`}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                {!activeFlatEstate && (
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 7px', borderRadius: 4, background: 'rgba(22,160,133,0.1)', border: '1px solid rgba(22,160,133,0.25)', color: '#1abc9c', fontSize: '0.6rem', fontFamily: "'JetBrains Mono', monospace" }}>
                    <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#1abc9c' }} /> LIVE
                  </span>
                )}
                {activeFlatEstate && (
                  <button
                    onClick={() => { setActiveFlatEstate(null); setDrillFlats([]); setSelectedFlat(null); setHoveredFlatIdx(null); }}
                    style={{ background: 'none', border: '1px solid #1a5c3a', color: '#27ae60', cursor: 'pointer', fontSize: '0.65rem', padding: '3px 8px', borderRadius: 4, lineHeight: 1, whiteSpace: 'nowrap' }}
                  >← Estates</button>
                )}
              </div>
            </div>

            {/* Compact grant/budget bar */}
            {derived?.grants && (
              <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', padding: '6px 8px', background: '#161616', borderRadius: 6, border: '1px solid #1e1e1e' }}>
                {derived.grants.total > 0 && (
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.56rem', color: '#555', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Grants</div>
                    <div style={{ fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace", color: '#27ae60', fontWeight: 600 }}>${derived.grants.total.toLocaleString()}</div>
                  </div>
                )}
                {derived.grants.total > 0 && <div style={{ width: 1, height: 20, background: '#2a2a2a' }} />}
                <div style={{ textAlign: 'center', flex: 1 }}>
                  <div style={{ fontSize: '0.56rem', color: '#555', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Effective Budget</div>
                  <div style={{ fontSize: '0.8rem', fontFamily: "'JetBrains Mono', monospace", color: '#27ae60', fontWeight: 700 }}>~${effectiveBudget?.toLocaleString() || '—'}</div>
                </div>
                {rawCount > 0 && (
                  <>
                    <div style={{ width: 1, height: 20, background: '#2a2a2a' }} />
                    <div style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '0.56rem', color: '#555', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Transactions</div>
                      <div style={{ fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace", color: '#aaa', fontWeight: 600 }}>{rawCount.toLocaleString()}</div>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>

          {/* Body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px' }}>

            {/* Phase 1: estate cards */}
            {!activeFlatEstate && recs.slice(0, 5).map((rec, i) => {
              const isSel = selectedEstate === rec.town;
              const tr = rec.pd?.trend12;
              const scCls = rec.sc.total >= 75 ? '#27ae60' : rec.sc.total >= 55 ? '#d4a843' : '#e67e22';
              const confCol = rec.pd.conf === 'high' ? '#55d98d' : rec.pd.conf === 'medium' ? '#e67e22' : '#ff8080';
              const activeCrit = rec.sc.active?.length ? rec.sc.active : ['budget', 'flat', 'region', 'mrt', 'amenity'];
              const CRIT_META = {
                budget:  { icon: '💰', label: 'Budget',    data: rec.sc.budget },
                flat:    { icon: '🏠', label: 'Flat',      data: rec.sc.flat },
                region:  { icon: '🗺️', label: 'Region',    data: rec.sc.region },
                lease:   { icon: '📅', label: 'Lease',     data: rec.sc.lease },
                mrt:     { icon: '🚇', label: 'Transport', data: rec.sc.transport },
                amenity: { icon: '📍', label: 'Amenity',   data: rec.sc.amenity },
              };
              return (
                <div key={rec.town}
                  onClick={() => setSelectedEstate(rec.town)}
                  style={{
                    background: isSel ? '#0a1f12' : '#181818',
                    border: `1px solid ${isSel ? '#27ae60' : '#2a2a2a'}`,
                    borderRadius: 8, padding: '10px 12px', marginBottom: 8, cursor: 'pointer', transition: 'border-color 0.15s',
                  }}
                  onMouseEnter={e => { if (!isSel) e.currentTarget.style.borderColor = '#3a3a3a'; }}
                  onMouseLeave={e => { if (!isSel) e.currentTarget.style.borderColor = '#2a2a2a'; }}
                >
                  {/* Row 1: rank + name + score */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ minWidth: 22, height: 22, borderRadius: '50%', background: '#27ae60', color: '#fff', fontSize: '0.65rem', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'JetBrains Mono', monospace", flexShrink: 0, marginTop: 1 }}>{i + 1}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#e0e0e0' }}>{rec.town}</div>
                        <div style={{ textAlign: 'right' }}>
                          <span style={{ fontSize: '0.82rem', fontFamily: "'JetBrains Mono', monospace", color: scCls, fontWeight: 700 }}>{rec.sc.total}</span>
                          <span style={{ fontSize: '0.6rem', color: '#555' }}>/100</span>
                        </div>
                      </div>
                      {/* Score bar */}
                      <div style={{ height: 3, background: '#2a2a2a', borderRadius: 2, marginTop: 4, overflow: 'hidden' }}>
                        <div style={{ height: '100%', borderRadius: 2, background: `linear-gradient(90deg, #c0392b, #e67e22, #f1c40f, #27ae60)`, width: `${rec.sc.total}%`, transition: 'width 0.4s' }} />
                      </div>
                      {/* Label + subtitle */}
                      <div style={{ marginTop: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.62rem', color: scCls, fontWeight: 600 }}>{rec.sc.label || ''}</span>
                        <span style={{ fontSize: '0.6rem', color: '#444' }}>{rec.pd.n} txn · {rec.pd.conf}</span>
                      </div>

                      {/* Price + stats row */}
                      <div style={{ marginTop: 5, display: 'flex', gap: 5, flexWrap: 'wrap', fontSize: '0.65rem', color: '#666' }}>
                        <span style={{ color: '#d4a843' }}>${(rec.pd.p25/1000).toFixed(0)}k–${(rec.pd.p75/1000).toFixed(0)}k</span>
                        <span>·</span>
                        <span>${(rec.pd.median/1000).toFixed(0)}k med</span>
                        <span>·</span>
                        <span>${rec.pd.psm.toLocaleString()}/sqm</span>
                        {tr !== undefined && <><span>·</span><span style={{ color: tr > 0 ? '#e67e22' : '#27ae60' }}>{tr > 0 ? '▲' : '▼'}{Math.abs(tr)}%</span></>}
                      </div>

                      {/* Criteria pills — show active as ✓ labels, show pts/max only when max > 0 */}
                      <div style={{ marginTop: 5, display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                        {activeCrit.map(c => {
                          const m = CRIT_META[c];
                          if (!m?.data) return null;
                          const pts = m.data.pts ?? 0;
                          const max = m.data.max ?? 0;
                          if (max > 0) {
                            // Has real breakdown (e.g. amenity)
                            const frac = pts / max;
                            const col = frac >= 0.75 ? '#27ae60' : frac >= 0.5 ? '#d4a843' : '#e67e22';
                            return (
                              <span key={c} style={{ fontSize: '0.58rem', padding: '1px 5px', borderRadius: 3, background: '#1e1e1e', color: '#888', border: '1px solid #2a2a2a' }}>
                                {m.icon} {m.label} <span style={{ color: col, fontWeight: 600 }}>{pts}/{max}</span>
                              </span>
                            );
                          }
                          // Budget: warn if estate median exceeds effective budget
                          let warn = false;
                          if (c === 'budget' && rec.effective > 0 && rec.pd.median > rec.effective) warn = true;
                          return (
                            <span key={c} style={{ fontSize: '0.58rem', padding: '1px 5px', borderRadius: 3, background: '#1e1e1e', color: '#555', border: '1px solid #222' }}>
                              {m.icon} <span style={{ color: '#888' }}>{m.label}</span> <span style={{ color: warn ? '#ff8080' : '#27ae60' }}>{warn ? '⚠' : '✓'}</span>
                            </span>
                          );
                        })}
                      </div>

                      {/* Expanded when selected */}
                      {isSel && (
                        <div style={{ marginTop: 8 }}>
                          {/* Why text */}
                          <div style={{ fontSize: '0.68rem', color: '#888', lineHeight: 1.5, fontStyle: 'italic', padding: '6px 8px', background: '#1a1a1a', borderRadius: 5, borderLeft: '2px solid #27ae60', marginBottom: 8 }}>
                            {whyText(rec.town, rec.ftype, rec.sc.total, rec.pd, rec.effective)}
                          </div>
                          <button
                            onClick={e => { e.stopPropagation(); setActiveFlatEstate(rec.town); loadFlats({ estate: rec.town }); }}
                            style={{ width: '100%', background: '#27ae60', color: '#fff', border: 'none', borderRadius: 4, padding: '5px 0', fontSize: '0.72rem', fontWeight: 700, cursor: 'pointer', letterSpacing: '0.3px' }}
                          >View 10 Flats →</button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Phase 2+3: estate scorecard at top + flat cards */}
            {activeFlatEstate && (() => {
              const estateRec = recs.find(r => r.town === activeFlatEstate);
              if (!estateRec) return null;
              const scCol = estateRec.sc.total >= 75 ? '#27ae60' : estateRec.sc.total >= 55 ? '#d4a843' : '#e67e22';
              return (
                <div style={{ background: '#161616', border: '1px solid #2a2a2a', borderRadius: 8, padding: '8px 10px', marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#e0e0e0' }}>{estateRec.town}</span>
                      <span style={{ fontSize: '0.6rem', color: scCol, fontWeight: 600 }}>{estateRec.sc.label}</span>
                    </div>
                    <span style={{ fontSize: '0.75rem', fontFamily: "'JetBrains Mono', monospace", color: scCol, fontWeight: 700 }}>{estateRec.sc.total}/100</span>
                  </div>
                  <div style={{ height: 2, background: '#2a2a2a', borderRadius: 1, overflow: 'hidden', marginBottom: 5 }}>
                    <div style={{ height: '100%', background: `linear-gradient(90deg, #c0392b, #e67e22, #f1c40f, #27ae60)`, width: `${estateRec.sc.total}%` }} />
                  </div>
                  <div style={{ display: 'flex', gap: 8, fontSize: '0.6rem', color: '#666', flexWrap: 'wrap' }}>
                    <span>Median <span style={{ color: '#aaa' }}>${(estateRec.pd.median/1000).toFixed(0)}k</span></span>
                    <span>${estateRec.pd.psm.toLocaleString()}/sqm</span>
                    <span>{estateRec.pd.n} txn</span>
                    {estateRec.pd.trend12 !== undefined && (
                      <span style={{ color: estateRec.pd.trend12 > 0 ? '#e67e22' : '#27ae60' }}>
                        {estateRec.pd.trend12 > 0 ? '▲' : '▼'}{Math.abs(estateRec.pd.trend12)}%
                      </span>
                    )}
                  </div>
                </div>
              );
            })()}
            {activeFlatEstate && drillLoading && (
              <div style={{ textAlign: 'center', paddingTop: 48, color: '#444', fontSize: '0.8rem' }}>Loading flats…</div>
            )}
            {activeFlatEstate && drillError && (
              <div style={{ color: '#c0392b', padding: '16px 8px', fontSize: '0.78rem' }}>{drillError}</div>
            )}
            {activeFlatEstate && !drillLoading && !drillError && filteredFlats.length === 0 && (
              <div style={{ textAlign: 'center', paddingTop: 48, color: '#444', fontSize: '0.8rem' }}>No listings found.</div>
            )}
            {activeFlatEstate && filteredFlats.map((flat, i) => {
              const over = effectiveBudget && flat.resale_price > effectiveBudget;
              const pct = effectiveBudget ? Math.abs(flat.resale_price - effectiveBudget) / effectiveBudget : 1;
              const nearBudget = pct <= 0.05;
              const isFlatSel = selectedFlat?._idx === i;
              const col = nearBudget ? '#27ae60' : over ? '#c0392b' : '#d4a843';
              const psm = flat.floor_area_sqm > 0 ? Math.round(flat.resale_price / flat.floor_area_sqm) : null;
              const budgetDelta = effectiveBudget ? flat.resale_price - effectiveBudget : null;
              const budgetPctStr = effectiveBudget ? `${over ? '+' : ''}${((flat.resale_price - effectiveBudget) / effectiveBudget * 100).toFixed(0)}%` : null;
              // Find the estate rec for this flat to show estate-level score context
              const estateRec = recs.find(r => r.town === activeFlatEstate);
              return (
                <div key={i}
                  onMouseEnter={() => setHoveredFlatIdx(i)}
                  onMouseLeave={() => setHoveredFlatIdx(null)}
                  onClick={() => { setSelectedFlat({ ...flat, _idx: i }); if (flat.latitude && flyToFlatRef.current) flyToFlatRef.current(flat); }}
                  style={{
                    background: isFlatSel ? '#0a1f12' : nearBudget ? '#192419' : '#181818',
                    border: `1px solid ${isFlatSel ? '#27ae60' : nearBudget ? '#2a4a2a' : '#242424'}`,
                    borderRadius: 8, padding: '10px 12px', marginBottom: 8, cursor: 'pointer', transition: 'border-color 0.15s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 7 }}>
                    <div style={{ minWidth: 22, height: 22, borderRadius: '50%', background: col, color: '#fff', fontSize: '0.63rem', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'JetBrains Mono', monospace", flexShrink: 0, marginTop: 1 }}>{i + 1}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 6 }}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#d0d0d0', lineHeight: 1.3 }}>Blk {flat.block} {flat.street_name}</div>
                        <div style={{ textAlign: 'right', flexShrink: 0 }}>
                          <div style={{ fontSize: '0.78rem', fontFamily: "'JetBrains Mono', monospace", color: over ? '#e67e22' : '#27ae60', fontWeight: 700, whiteSpace: 'nowrap' }}>${flat.resale_price.toLocaleString()}</div>
                          {psm && <div style={{ fontSize: '0.58rem', color: '#555', fontFamily: "'JetBrains Mono', monospace" }}>${psm}/sqm</div>}
                        </div>
                      </div>
                      <div style={{ marginTop: 4, display: 'flex', gap: 6, flexWrap: 'wrap', fontSize: '0.65rem', color: '#555' }}>
                        <span>Floor {flat.storey_range_start}–{flat.storey_range_end}</span>
                        <span>·</span><span>{flat.floor_area_sqm} sqm</span>
                        <span>·</span><span>Lease {flat.remaining_lease_years}y{flat.remaining_lease_months > 0 ? ` ${flat.remaining_lease_months}m` : ''}</span>
                      </div>
                      <div style={{ marginTop: 3, fontSize: '0.62rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ color: '#3a3a3a' }}>Sold {flat.sold_date}</span>
                        <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          {budgetPctStr && !nearBudget && (
                            <span style={{ color: over ? '#e67e22' : '#27ae60', fontSize: '0.6rem', fontFamily: "'JetBrains Mono', monospace" }}>
                              {over ? '▲' : '▼'} {budgetPctStr} budget
                            </span>
                          )}
                          {isFlatSel
                            ? <span style={{ color: '#27ae60', fontWeight: 700 }}>📍 Selected</span>
                            : nearBudget && <span style={{ color: '#27ae60', fontWeight: 700 }}>✓ Near budget</span>}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Footer */}
          <div style={{ padding: '6px 14px', borderTop: '1px solid #242424', fontSize: '0.6rem', color: '#3a3a3a', display: 'flex', justifyContent: 'space-between' }}>
            <span>
              {activeFlatEstate
                ? `${filteredFlats.length} flats · click pin for amenities`
                : `Top ${Math.min(recs.length, 5)} of ${recs.length} estates · cosine similarity`}
            </span>
            {latestMonth && <span>{latestMonth} · data.gov.sg</span>}
          </div>
        </div>
      )}
    </div>
  );
}
