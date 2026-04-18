import { useEffect, useRef, useCallback, useState } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import { ALL_TOWNS, COORDS, AMENITIES } from '../constants';
import { rankToColor, whyText } from '../engine';
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

function MapContent({ recs, highlightedTown, onTownClick, mapRef, drillFlats, activeFlatEstate, onEstateSelect, effectiveBudget, flyToFlatRef, selectedEstate, hoveredFlatIdx, selectedFlat, onFilteredFlats, mustAmenities, onFlatAmenities }) {
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

  const mustAmenitiesRef = useRef(mustAmenities);
  useEffect(() => { mustAmenitiesRef.current = mustAmenities; }, [mustAmenities]);

  const clearFlatAmenityMarkers = useCallback(() => {
    amenityMarkersPhase3Ref.current.forEach(m => map.removeLayer(m));
    amenityMarkersPhase3Ref.current = [];
  }, [map]);

  // Config for each amenity type shown in Phase 3
  const FLAT_AMENITY_CFG = {
    parks:     { color: '#27ae60', emoji: '🌳', label: 'Park',      threshold: '1km',  mustKey: 'park' },
    hawkers:   { color: '#e67e22', emoji: '🍜', label: 'Hawker',    threshold: '1km',  mustKey: 'hawker' },
    mrts:      { color: '#3498db', emoji: '🚇', label: 'MRT',       threshold: '1km',  mustKey: 'mrt' },
    schools:   { color: '#9b59b6', emoji: '🏫', label: 'School',    threshold: '1km',  mustKey: 'school' },
    malls:     { color: '#f3e412', emoji: '🛍️', label: 'Mall',      threshold: '1.5km', mustKey: 'mall' },
    hospitals: { color: '#e74c3c', emoji: '🏥', label: 'Hospital',  threshold: '3km',  mustKey: 'hospital' },
  };

  const showFlatAmenityMarkers = useCallback((amenities, flatLat, flatLng) => {
    clearFlatAmenityMarkers();
    // amenities may be the old { parks: [...] } shape or a flat array (legacy)
    const byType = Array.isArray(amenities)
      ? { parks: amenities }
      : amenities;

    const hasMust = mustAmenities?.length > 0;
    Object.entries(byType).forEach(([type, items]) => {
      if (!items?.length) return;
      const cfg = FLAT_AMENITY_CFG[type] || { color: '#888', emoji: '📍', label: type, mustKey: type };
      const isMust = hasMust && mustAmenities.includes(cfg.mustKey);
      const opacity = hasMust && !isMust ? 0.25 : 1;
      items.forEach(item => {
        // support legacy park_name key; for hawkers show only the text inside () if present
        const rawName = item.name || item.park_name || '';
        const parenMatch = type === 'hawkers' && rawName.match(/\(([^)]+)\)/);
        const name = parenMatch ? parenMatch[1] : rawName;
        // MRT line code badges
        const MRT_LINE_META = {
          'CIRCLE LINE':        { code: 'CCL', color: '#fa9e0d' },
          'DOWNTOWN LINE':      { code: 'DTL', color: '#005ec4' },
          'EAST WEST LINE':     { code: 'EWL', color: '#009645' },
          'NORTH EAST LINE':    { code: 'NEL', color: '#9900aa' },
          'NORTH SOUTH LINE':   { code: 'NSL', color: '#d42e12' },
          'THOMSON-EAST COAST LINE': { code: 'TEL', color: '#9D5B25' },
        };
        const lineBadges = type === 'mrts' && item.lines?.length
          ? item.lines.map(l => {
              const m = MRT_LINE_META[l];
              return m ? `<span style="background:${m.color};color:#fff;border-radius:3px;padding:1px 4px;font-size:8px;font-weight:700;letter-spacing:.3px;margin-right:2px">${m.code}</span>` : '';
            }).join('')
          : '';
        const icon = L.divIcon({
          html: `<div style="display:flex;align-items:center;gap:6px;opacity:${opacity}"><div style="background:${cfg.color};width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;border:2px solid #0f0f0f;box-shadow:0 2px 8px rgba(0,0,0,.7);flex-shrink:0">${cfg.emoji}</div><span style="background:rgba(15,15,15,0.82);color:#fff;border-radius:4px;padding:2px 7px;font-size:10px;font-family:'DM Sans',sans-serif;font-weight:600;white-space:nowrap;letter-spacing:.3px">${lineBadges}${name} · ${item.distance.toFixed(2)}km</span></div>`,
          className: '', iconAnchor: [14, 14],
        });
        const m = L.marker([item.latitude, item.longitude], { icon }).addTo(map);
        const line = L.polyline(
          [[flatLat, flatLng], [item.latitude, item.longitude]],
          { color: cfg.color, weight: 1.5, dashArray: '4 4', opacity: hasMust && !isMust ? 0.15 : 0.6 }
        ).addTo(map);
        amenityMarkersPhase3Ref.current.push(m, line);
      });
    });
  }, [map, clearFlatAmenityMarkers, mustAmenities]);

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
        onFlatAmenities?.(amenities, mustAmenitiesRef.current ?? []);
      })
      .catch(() => {});
  }, [map, onFlatAmenities]);
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
        html: `<div style="display:flex;align-items:center;gap:6px"><div style="background:${def.color};width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;border:2px solid #0f0f0f;box-shadow:0 2px 8px rgba(0,0,0,.7);flex-shrink:0">${def.icon}</div><span style="background:rgba(15,15,15,0.82);color:#fff;border-radius:4px;padding:2px 7px;font-size:11px;font-family:'DM Sans',sans-serif;font-weight:600;white-space:nowrap;letter-spacing:.3px">${def.label}${def.mins ? ' · ' + def.mins + 'm' : ''}</span></div>`,
        className: '', iconAnchor: [14, 14],
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
        const rank = rec ? recs.indexOf(rec) + 1 : null;
        const total = recs.length;
        const col = rank !== null ? rankToColor(rank, total) : '#3d3d3d';

        const baseStyle = {
          fillColor: '#3d3d3d',
          fillOpacity: rec ? 0.15 : 0.08,
          color: '#444',
          weight: rec ? 1.0 : 0.6,
          opacity: rec ? 0.5 : 0.3,
        };
        const layer = L.geoJSON(feat, { style: baseStyle, interactive: true });

        const am = AMENITIES[town] || {};
        let popupHtml;
        if (rec) {
          popupHtml = `
            <div style="font-size:.9rem;font-weight:600;margin-bottom:3px">#${rank} ${town}</div>
            <div style="font-size:.72rem;color:#888;margin-bottom:8px">${rec.ftype} · Rank: <strong style="color:${col}">#${rank} of ${total}</strong></div>
            <div style="display:flex;gap:10px;margin-bottom:6px">
              <div><div style="font-size:.62rem;color:#666;text-transform:uppercase;letter-spacing:.8px">Price Range</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:.82rem;color:#d4a843">$${(rec.pd.p25/1000).toFixed(0)}k–$${(rec.pd.p75/1000).toFixed(0)}k</div></div>
              <div><div style="font-size:.62rem;color:#666;text-transform:uppercase;letter-spacing:.8px">Median</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:.82rem">$${rec.pd.median.toLocaleString()}</div></div>
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
      : new Set(recsRef.current.map(r => r.town));
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
        const recsArr = recsRef.current;
        const rankIdx = recsArr.findIndex(r => r.town === town);
        const estCol = rankIdx >= 0 ? rankToColor(rankIdx + 1, recsArr.length) : '#27ae60';
        const hotStyle = { fillColor: estCol, fillOpacity: fillOp, color: estCol, weight: w, opacity: 1 };
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
    const col = nearBudget ? '#d4a843' : over ? '#c0392b' : '#27ae60';
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
      const col = nearBudget ? '#d4a843' : over ? '#c0392b' : '#27ae60';
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
    recs.forEach((rec, i) => {
      const c = COORDS[rec.town];
      if (!c) return;
      const isSel = rec.town === selectedEstate;
      const size = isSel ? 34 : 28;
      const pinCol = rankToColor(i + 1, recs.length);
      const icon = L.divIcon({
        html: `<div style="background:${pinCol};color:#fff;border-radius:50%;width:${size}px;height:${size}px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:${isSel?12:11}px;border:${isSel?'2px solid #fff':'2px solid #0f0f0f'};box-shadow:0 ${isSel?4:2}px ${isSel?12:8}px rgba(0,0,0,.8);font-family:'JetBrains Mono',monospace">${i + 1}</div>`,
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
  const [flatAmenities, setFlatAmenities] = useState(null);
  const [flatMustAmenities, setFlatMustAmenities] = useState([]);
  const handleFilteredFlats = useCallback((flats) => setFilteredFlats(flats), []);
  const handleFlatAmenities = useCallback((amenities, snap) => {
    setFlatAmenities(amenities);
    setFlatMustAmenities(snap);
  }, []);

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
    const r = recs.find(x => x.town === town);
    setDrillFlats(r?.top_flats || []);
  }, [recs]);

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
    setFlatAmenities(null);
    setFlatMustAmenities([]);
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
    setFlatAmenities(null);
    setFlatMustAmenities([]);
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
        <MapContent recs={recs} highlightedTown={highlightedTown} onTownClick={handleTownClick} mapRef={mapRef} drillFlats={drillFlats} activeFlatEstate={activeFlatEstate} onEstateSelect={(town) => { const r = recs.find(x => x.town === town); setActiveFlatEstate(town); setDrillFlats(r?.top_flats || []); }} effectiveBudget={effectiveBudget} flyToFlatRef={flyToFlatRef} selectedEstate={selectedEstate} hoveredFlatIdx={hoveredFlatIdx} selectedFlat={selectedFlat} onFilteredFlats={handleFilteredFlats} mustAmenities={formState?.mustAmenities} onFlatAmenities={handleFlatAmenities} />
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
        <div className="font-serif text-[0.88rem] text-white mb-2">Estate Rank</div>
        <div className="h-2.5 rounded-[5px] bg-gradient-to-r from-[#c0392b] via-[#e67e22] via-50% via-[#f1c40f] to-[#27ae60] mb-1" />
        <div className="flex justify-between text-[0.62rem] text-muted">
          <span>#N Last</span><span>#1 Best</span>
        </div>
        {selectedFlat && (
          <div className="mt-2.5 pt-2 border-t border-dk4">
            <div className="text-[0.68rem] text-light mb-1.5 font-medium">Amenities Shown</div>
            {[
              ['#3498db', '🚇', 'MRT Station'],
              ['#e67e22', '🍜', 'Hawker Centre'],
              ['#27ae60', '🌳', 'Park'],
              ['#9b59b6', '🏫', 'Pri School'],
              ['#f3e412', '🛍️', 'Mall'],
              ['#e74c3c', '🏥', 'Hospital'],
            ].map(([color, icon, label]) => (
              <div key={label} className="flex items-center gap-1.5 mb-1 text-[0.68rem]">
                <span style={{ color }}>{icon}</span>
                {label}
              </div>
            ))}
          </div>
        )}
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
                    : `${recs.length} Estates`}
                </div>
                <div style={{ fontSize: '0.68rem', color: '#555', marginTop: 2 }}>
                  {activeFlatEstate
                    ? `${formState?.ftype || ''} · hover card to highlight · click to zoom`
                    : `${formState?.ftype || 'Any type'} · cosine similarity · ${recs[0]?.sc?.active?.length || 0} criteria`}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                {activeFlatEstate && (
                  <button
                    onClick={() => { setActiveFlatEstate(null); setDrillFlats([]); setSelectedFlat(null); setHoveredFlatIdx(null); }}
                    style={{ background: 'none', border: '1px solid #1a5c3a', color: '#27ae60', cursor: 'pointer', fontSize: '0.65rem', padding: '3px 8px', borderRadius: 4, lineHeight: 1, whiteSpace: 'nowrap' }}
                  >← Estates</button>
                )}
              </div>
            </div>

            {/* Budget breakdown bar */}
            {derived?.grants && (
              <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', background: '#161616', borderRadius: 6, border: '1px solid #1e1e1e', overflow: 'hidden' }}>
                {[
                  { label: 'Cash + CPF',  value: `$${((formState?.cash ?? 0) + (formState?.cpf ?? 0)).toLocaleString()}`, color: '#aaa' },
                  { label: 'Grants',      value: derived.grants.total > 0 ? `$${derived.grants.total.toLocaleString()}` : '—', color: '#27ae60' },
                  { label: 'HDB Loan',    value: derived.loanAmt > 0 ? `$${derived.loanAmt.toLocaleString()}` : '—', color: '#3498db' },
                  { label: 'Total Budget', value: `~$${effectiveBudget?.toLocaleString() || '—'}`, color: '#27ae60' },
                ].map(({ label, value, color }, idx, arr) => (
                  <div key={label} style={{ textAlign: 'center', padding: '6px 4px', borderRight: idx < arr.length - 1 ? '1px solid #252525' : 'none' }}>
                    <div style={{ fontSize: '0.52rem', color: '#555', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 2 }}>{label}</div>
                    <div style={{ fontSize: '0.72rem', fontFamily: "'JetBrains Mono', monospace", color, fontWeight: 700, whiteSpace: 'nowrap' }}>{value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 10px' }}>

            {/* Phase 1: estate cards — sorted by avg_score desc */}
            {!activeFlatEstate && [...recs].sort((a, b) => (b.avg_score ?? 0) - (a.avg_score ?? 0)).map((rec, i) => {
              const isSel = selectedEstate === rec.town;
              const bestScore  = rec.sc.total;                          // best flat × 100
              const avgScore   = Math.round((rec.avg_score ?? 0) * 100);
              const strong     = rec.strong_matches ?? 0;
              const topN       = (rec.top_flats || []).length;
              const avgCol     = avgScore >= 75 ? '#27ae60' : avgScore >= 55 ? '#d4a843' : '#e67e22';
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
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ minWidth: 22, height: 22, borderRadius: '50%', background: rankToColor(i + 1, recs.length), color: '#fff', fontSize: '0.65rem', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'JetBrains Mono', monospace", flexShrink: 0, marginTop: 1 }}>{i + 1}</div>
                    <div style={{ flex: 1 }}>
                      {/* Row 1: name + txn count */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#e0e0e0' }}>{rec.town}</div>
                        <span style={{ fontSize: '0.6rem', color: '#444' }}>{rec.pd.n} txn · {rec.pd.conf}</span>
                      </div>

                      {/* Score summary bar */}
                      <div style={{ marginTop: 5, padding: '5px 8px', background: '#111', borderRadius: 5, border: '1px solid #222', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                        <div style={{ textAlign: 'center', flex: 1 }}>
                          <div style={{ fontSize: '0.55rem', color: '#444', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 1 }}>Avg</div>
                          <div style={{ fontSize: '0.82rem', fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: avgCol }}>{avgScore}<span style={{ fontSize: '0.55rem', color: '#444' }}>/100</span></div>
                        </div>
                        <div style={{ width: 1, height: 28, background: '#2a2a2a' }} />
                        <div style={{ textAlign: 'center', flex: 1 }}>
                          <div style={{ fontSize: '0.55rem', color: '#444', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 1 }}>Best</div>
                          <div style={{ fontSize: '0.82rem', fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: '#aaa' }}>{bestScore}<span style={{ fontSize: '0.55rem', color: '#444' }}>/100</span></div>
                        </div>
                        <div style={{ width: 1, height: 28, background: '#2a2a2a' }} />
                        <div style={{ textAlign: 'center', flex: 1 }}>
                          <div style={{ fontSize: '0.55rem', color: '#444', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 1 }}>Strong</div>
                          <div style={{ fontSize: '0.82rem', fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: strong > 0 ? '#27ae60' : '#555' }}>{strong}<span style={{ fontSize: '0.6rem', color: '#444' }}>/{topN}</span></div>
                        </div>
                      </div>

                      {/* Avg score bar */}
                      <div style={{ height: 3, background: '#2a2a2a', borderRadius: 2, marginTop: 5, overflow: 'hidden' }}>
                        <div style={{ height: '100%', borderRadius: 2, background: `linear-gradient(90deg, #c0392b, #e67e22, #f1c40f, #27ae60)`, width: `${avgScore}%`, transition: 'width 0.4s' }} />
                      </div>

                      {/* Baseline comparison row */}
                      {(rec.baseline_price_rank != null || rec.baseline_pop_rank != null) && (
                        <div style={{ marginTop: 5, display: 'flex', gap: 6, alignItems: 'center', fontSize: '0.58rem', color: '#444' }}>
                          <span style={{ textTransform: 'uppercase', letterSpacing: '0.4px', color: '#333' }}>vs baselines</span>
                          {rec.baseline_price_rank != null && (() => {
                            const diff = rec.baseline_price_rank - (i + 1);
                            const col = diff > 0 ? '#27ae60' : diff < 0 ? '#e67e22' : '#555';
                            const arrow = diff > 0 ? '▲' : diff < 0 ? '▼' : '=';
                            return (
                              <span style={{ padding: '1px 5px', borderRadius: 3, background: '#1a1a1a', border: '1px solid #252525' }}>
                                💰 Price <span style={{ color: col, fontWeight: 600 }}>{arrow}{Math.abs(diff) || '='} #{rec.baseline_price_rank}</span>
                              </span>
                            );
                          })()}
                          {rec.baseline_pop_rank != null && (() => {
                            const diff = rec.baseline_pop_rank - (i + 1);
                            const col = diff > 0 ? '#27ae60' : diff < 0 ? '#e67e22' : '#555';
                            const arrow = diff > 0 ? '▲' : diff < 0 ? '▼' : '=';
                            return (
                              <span style={{ padding: '1px 5px', borderRadius: 3, background: '#1a1a1a', border: '1px solid #252525' }}>
                                📊 Popularity <span style={{ color: col, fontWeight: 600 }}>{arrow}{Math.abs(diff) || '='} #{rec.baseline_pop_rank}</span>
                              </span>
                            );
                          })()}
                        </div>
                      )}

                      {/* Price row */}
                      <div style={{ marginTop: 5, display: 'flex', gap: 5, flexWrap: 'wrap', fontSize: '0.65rem', color: '#666' }}>
                        <span style={{ color: '#d4a843' }}>${(rec.pd.p25/1000).toFixed(0)}k–${(rec.pd.p75/1000).toFixed(0)}k</span>
                        <span>·</span>
                        <span>${(rec.pd.median/1000).toFixed(0)}k med</span>
                        <span>·</span>
                        <span>${rec.pd.psm.toLocaleString()}/sqm</span>
                      </div>

                      {/* Criteria pills — removed: budget/flat always active (no info),
                         amenity detail now shown in per-flat score breakdown */}

                      {/* Expanded when selected */}
                      {isSel && (
                        <div style={{ marginTop: 8 }}>
                          <div style={{ fontSize: '0.68rem', color: '#888', lineHeight: 1.5, fontStyle: 'italic', padding: '6px 8px', background: '#1a1a1a', borderRadius: 5, borderLeft: '2px solid #27ae60', marginBottom: 8 }}>
                            {whyText(rec.town, rec.ftype, rec.sc.total, rec.pd, rec.effective, rec.sc.active, rec.avg_score, rec.qualifying_flats)}
                          </div>
                          <button
                            onClick={e => { e.stopPropagation(); setActiveFlatEstate(rec.town); setDrillFlats(rec.top_flats || []); }}
                            style={{ width: '100%', background: '#27ae60', color: '#fff', border: 'none', borderRadius: 4, padding: '5px 0', fontSize: '0.72rem', fontWeight: 700, cursor: 'pointer', letterSpacing: '0.3px' }}
                          >View {(rec.top_flats || []).length} Flats →</button>
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
              const avgScore = Math.round((estateRec.avg_score ?? 0) * 100);
              const bestScore = estateRec.sc.total;
              const strong = estateRec.strong_matches ?? 0;
              const topN = (estateRec.top_flats || []).length;
              const avgCol = avgScore >= 75 ? '#27ae60' : avgScore >= 55 ? '#d4a843' : '#e67e22';
              return (
                <div style={{ background: '#161616', border: '1px solid #2a2a2a', borderRadius: 8, padding: '8px 10px', marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#e0e0e0' }}>{estateRec.town}</span>
                    <span style={{ fontSize: '0.6rem', color: '#444' }}>{estateRec.pd.n} txn</span>
                  </div>
                  <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
                    <div style={{ flex: 1, textAlign: 'center', padding: '4px 0', background: '#111', borderRadius: 4, border: '1px solid #222' }}>
                      <div style={{ fontSize: '0.52rem', color: '#444', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Avg</div>
                      <div style={{ fontSize: '0.78rem', fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: avgCol }}>{avgScore}/100</div>
                    </div>
                    <div style={{ flex: 1, textAlign: 'center', padding: '4px 0', background: '#111', borderRadius: 4, border: '1px solid #222' }}>
                      <div style={{ fontSize: '0.52rem', color: '#444', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Best</div>
                      <div style={{ fontSize: '0.78rem', fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: '#aaa' }}>{bestScore}/100</div>
                    </div>
                    <div style={{ flex: 1, textAlign: 'center', padding: '4px 0', background: '#111', borderRadius: 4, border: '1px solid #222' }}>
                      <div style={{ fontSize: '0.52rem', color: '#444', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Strong</div>
                      <div style={{ fontSize: '0.78rem', fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: strong > 0 ? '#27ae60' : '#555' }}>{strong}/{topN}</div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8, fontSize: '0.6rem', color: '#666', flexWrap: 'wrap' }}>
                    <span>Median <span style={{ color: '#aaa' }}>${(estateRec.pd.median/1000).toFixed(0)}k</span></span>
                    <span>${estateRec.pd.psm.toLocaleString()}/sqm</span>
                  </div>
                </div>
              );
            })()}
            {activeFlatEstate && drillLoading && (
              <div style={{ textAlign: 'center', paddingTop: 48, color: '#444', fontSize: '0.8rem' }}>Loading flats…</div>
            )}
            {activeFlatEstate && !drillLoading && filteredFlats.length > 0 && (
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '4px 6px', marginBottom: 6, background: '#161616', borderRadius: 5, border: '1px solid #1e1e1e', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.58rem', color: '#444', textTransform: 'uppercase', letterSpacing: '0.5px', marginRight: 2 }}>Pin colour</span>
                {[['#27ae60', 'under budget'], ['#d4a843', '≈ budget'], ['#c0392b', 'over budget']].map(([col, label]) => (
                  <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.6rem', color: '#666' }}>
                    <span style={{ width: 8, height: 8, borderRadius: '50%', background: col, display: 'inline-block', flexShrink: 0 }} />
                    {label}
                  </span>
                ))}
              </div>
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
              const col = nearBudget ? '#d4a843' : over ? '#c0392b' : '#27ae60';
              const psm = flat.floor_area_sqm > 0 ? Math.round(flat.resale_price / flat.floor_area_sqm) : null;
              const budgetDelta = effectiveBudget ? flat.resale_price - effectiveBudget : null;
              const budgetPctStr = effectiveBudget ? `${over ? '+' : ''}${((flat.resale_price - effectiveBudget) / effectiveBudget * 100).toFixed(0)}%` : null;
              return (
                <div key={i}
                  onMouseEnter={() => setHoveredFlatIdx(i)}
                  onMouseLeave={() => setHoveredFlatIdx(null)}
                  onClick={() => { setSelectedFlat({ ...flat, _idx: i }); setFlatAmenities(null); setFlatMustAmenities([]); if (flat.latitude && flyToFlatRef.current) flyToFlatRef.current(flat); }}
                  style={{
                    background: isFlatSel ? '#0a1f12' : '#181818',
                    border: `1px solid ${isFlatSel ? '#27ae60' : '#242424'}`,
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
                          {flat.score != null && <div style={{ fontSize: '0.62rem', color: '#1abc9c', fontFamily: "'JetBrains Mono', monospace", fontWeight: 600 }}>{Math.round(flat.score * 100)}/100</div>}
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

                      {/* Nearby amenities — shown for each selected must-have when flat is selected */}
                      {isFlatSel && flatAmenities && flatMustAmenities.length > 0 && (() => {
                        const AMEN_CFG = {
                          mrt:      { dataKey: 'mrts',      icon: '🚇', color: '#3498db', title: 'Nearby MRT Stations',    strip: ' MRT STATION' },
                          hawker:   { dataKey: 'hawkers',   icon: '🍜', color: '#e67e22', title: 'Nearby Hawker Centres',  parenOnly: true },
                          park:     { dataKey: 'parks',     icon: '🌳', color: '#27ae60', title: 'Nearby Parks' },
                          school:   { dataKey: 'schools',   icon: '🏫', color: '#9b59b6', title: 'Nearby Primary Schools' },
                          mall:     { dataKey: 'malls',     icon: '🛍️', color: '#f3e412', title: 'Nearby Shopping Malls' },
                          hospital: { dataKey: 'hospitals', icon: '🏥', color: '#e74c3c', title: 'Nearby Public Hospitals' },
                        };
                        const MRT_LINE_META = {
                          'CIRCLE LINE':             { code: 'CCL', color: '#fa9e0d' },
                          'DOWNTOWN LINE':           { code: 'DTL', color: '#005ec4' },
                          'EAST WEST LINE':          { code: 'EWL', color: '#009645' },
                          'NORTH EAST LINE':         { code: 'NEL', color: '#9900aa' },
                          'NORTH SOUTH LINE':        { code: 'NSL', color: '#d42e12' },
                          'THOMSON-EAST COAST LINE': { code: 'TEL', color: '#9D5B25' },
                        };
                        return (flatMustAmenities).map(amenKey => {
                          const cfg = AMEN_CFG[amenKey];
                          if (!cfg) return null;
                          const items = flatAmenities[cfg.dataKey];
                          if (!items?.length) return null;
                          const unique = [...new Map(items.map(m => [m.name, m])).values()].sort((a, b) => a.distance - b.distance);
                          return (
                            <div key={amenKey} style={{ marginTop: 8, background: '#111', border: `1px solid ${cfg.color}33`, borderRadius: 6, padding: '8px 10px', fontSize: '0.62rem' }}>
                              <div style={{ fontSize: '0.65rem', fontWeight: 700, color: cfg.color, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.5px' }}>{cfg.icon} {cfg.title}</div>
                              {unique.map((item, idx) => {
                                const rawName = item.name || '';
                                const parenMatch = cfg.parenOnly && rawName.match(/\(([^)]+)\)/);
                                const displayName = parenMatch ? parenMatch[1] : cfg.strip ? rawName.replace(cfg.strip, '') : rawName;
                                const lineBadges = amenKey === 'mrt' && item.lines?.length
                                  ? item.lines.map(l => {
                                      const lm = MRT_LINE_META[l];
                                      return lm
                                        ? <span key={l} style={{ background: lm.color, color: '#fff', borderRadius: 3, padding: '1px 4px', fontSize: '0.55rem', fontWeight: 700, letterSpacing: '0.3px', marginRight: 3 }}>{lm.code}</span>
                                        : null;
                                    })
                                  : null;
                                return (
                                  <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '3px 0', borderTop: idx > 0 ? '1px solid #1a1a1a' : 'none' }}>
                                    <span style={{ color: '#aaa', display: 'flex', alignItems: 'center', gap: 2 }}>{lineBadges}{displayName}</span>
                                    <span style={{ color: '#555', fontFamily: "'JetBrains Mono', monospace", flexShrink: 0, marginLeft: 8 }}>{item.distance.toFixed(2)} km</span>
                                  </div>
                                );
                              })}
                            </div>
                          );
                        });
                      })()}

                      {/* Score Breakdown Table — shown when flat is selected */}
                      {isFlatSel && flat.score_breakdown && (
                        <div style={{ marginTop: 8, background: '#111', border: '1px solid #222', borderRadius: 6, padding: '8px 10px', fontSize: '0.62rem' }}>
                          <div style={{ fontSize: '0.65rem', fontWeight: 700, color: '#888', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Score Breakdown</div>
                          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                              <tr style={{ color: '#444', fontSize: '0.55rem', textTransform: 'uppercase', letterSpacing: '0.3px' }}>
                                <th style={{ textAlign: 'left', paddingBottom: 4 }}>Criterion</th>
                                <th style={{ textAlign: 'center', paddingBottom: 4 }}>Match</th>
                                <th style={{ textAlign: 'right', paddingBottom: 4 }}>Pts</th>
                              </tr>
                            </thead>
                            <tbody>
                              {flat.score_breakdown.map((row) => {
                                const ptsRaw = row.contrib * 100;
                                const pts = row.dim === 'budget' ? ptsRaw : ptsRaw;
                                const ptsStr = row.dim === 'budget'
                                  ? (pts === 0 ? '—' : pts.toFixed(1))
                                  : pts.toFixed(1);
                                const isBudget = row.dim === 'budget';
                                const matchPct = isBudget
                                  ? (row.flat && row.buyer ? Math.round(row.flat / row.buyer * 100) : null)
                                  : Math.round(Math.min(row.flat, row.buyer) / Math.max(row.flat, row.buyer, 0.01) * 100);
                                const barCol = isBudget
                                  ? (pts < 0 ? '#e67e22' : '#27ae60')
                                  : row.priority
                                    ? (matchPct >= 70 ? '#27ae60' : matchPct >= 40 ? '#d4a843' : '#e67e22')
                                    : '#555';
                                const barWidth = isBudget
                                  ? Math.min(Math.abs(pts) / 5 * 100, 100)
                                  : Math.min(Math.abs(pts) / 0.2 * 100, 100);  // scale: 0.20 contrib = full bar
                                return (
                                  <tr key={row.dim} style={{ borderTop: '1px solid #1a1a1a' }}>
                                    <td style={{ padding: '4px 0', display: 'flex', alignItems: 'center', gap: 4 }}>
                                      <span>{row.icon}</span>
                                      <span style={{ color: row.priority ? '#e0e0e0' : '#666', fontWeight: row.priority ? 600 : 400 }}>
                                        {row.dim.charAt(0).toUpperCase() + row.dim.slice(1)}
                                      </span>
                                      {row.priority && <span style={{ fontSize: '0.5rem', color: '#1abc9c', fontWeight: 700 }}>★</span>}
                                    </td>
                                    <td style={{ padding: '4px 6px' }}>
                                      <div style={{ height: 4, background: '#222', borderRadius: 2, overflow: 'hidden' }}>
                                        <div style={{ height: '100%', borderRadius: 2, background: barCol, width: `${barWidth}%`, transition: 'width 0.3s' }} />
                                      </div>
                                    </td>
                                    <td style={{ textAlign: 'right', padding: '4px 0', fontFamily: "'JetBrains Mono', monospace", fontWeight: 600, color: isBudget && pts < 0 ? '#e67e22' : barCol, whiteSpace: 'nowrap' }}>
                                      {ptsStr}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                            <tfoot>
                              <tr style={{ borderTop: '1px solid #333' }}>
                                <td style={{ padding: '5px 0', fontWeight: 700, color: '#e0e0e0' }}>Total</td>
                                <td />
                                <td style={{ textAlign: 'right', padding: '5px 0', fontFamily: "'JetBrains Mono', monospace", fontWeight: 700, color: '#1abc9c', fontSize: '0.7rem' }}>
                                  {Math.round(flat.score * 100)}/100
                                </td>
                              </tr>
                            </tfoot>
                          </table>
                          {/* Score context — explains what criteria drove the score */}
                          {(() => {
                            const priority = flat.score_breakdown.filter(r => r.priority);
                            const nonBudget = priority.filter(r => r.dim !== 'budget');
                            const dimLabels = { floor: 'floor', mrt: 'MRT', hawker: 'hawker', mall: 'mall', park: 'park', school: 'school', hospital: 'hospital' };
                            const names = nonBudget.map(r => dimLabels[r.dim] || r.dim);
                            const totalScore = Math.round(flat.score * 100);
                            const conf = nonBudget.length === 0 ? 'Low' : nonBudget.length <= 2 ? 'Moderate' : 'High';
                            const confCol = nonBudget.length === 0 ? '#e67e22' : nonBudget.length <= 2 ? '#d4a843' : '#27ae60';
                            return (
                              <div style={{ marginTop: 6, fontSize: '0.55rem', color: '#555', lineHeight: 1.5 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                  <span style={{ color: confCol, fontWeight: 600 }}>{conf} confidence</span>
                                  <span>·</span>
                                  <span>{nonBudget.length} of {flat.score_breakdown.length - 1} preferences active</span>
                                </div>
                                <div style={{ marginTop: 2 }}>
                                  {names.length === 0
                                    ? 'No preferences set — score reflects general amenity proximity'
                                    : `Based on ${names.join(', ')}`}
                                </div>
                              </div>
                            );
                          })()}
                        </div>
                      )}
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
                : `${recs.length} estates · flats ranked by cosine similarity`}
            </span>
            {latestMonth && <span>{latestMonth} · data.gov.sg</span>}
          </div>
        </div>
      )}
    </div>
  );
}
