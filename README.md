# RS-PM-2026-01-17-IS08PT-GRP-HDB

## HDB Estate Recommender — Singapore

A React + Tailwind CSS web app that recommends HDB resale estates based on your buyer profile, budget, and amenity preferences. It pulls live resale transaction data from [data.gov.sg](https://data.gov.sg), computes applicable grants (EHG, CPF Housing Grant, PHG), and scores/ranks estates across budget fit, transport access, amenities, and region match.

## Prerequisites

- [Node.js](https://nodejs.org/) v18 or later
- [Python](https://www.python.org/downloads/release/python-3143/) v3.14.3
- [MySql]
- [MySql Database] https://drive.google.com/file/d/17vZOFqCrUF0cgR47X_b9dV8bPYJwnrr1/view?usp=drive_link
- npm (comes with Node.js)

## Getting Started

```bash
# Clone the repo
git clone https://github.com/<your-org>/RS-PM-2026-01-17-IS08PT-GRP-HDB.git
cd RS-PM-2026-01-17-IS08PT-GRP-HDB

# Install dependencies
npm install

# Start the development server
npm run dev
```

The app will be available at `http://localhost:5173/`.

## Build for Production

```bash
npm run build
```

The output will be in the `dist/` folder, ready to be deployed to any static hosting provider.




---

## Data Sources

| File | Source | Dataset ID |
|---|---|---|
| `resale_prices.csv` | data.gov.sg | `d_8b84c4ee58e3cfc0ece0d773c8ca6abc` |
| `planning_areas.geojson` | data.gov.sg | `d_4765db0e87b9c86336792efe8a1f7a66` |
| `hawker_centres.geojson` | data.gov.sg (NEA) | `d_4a086da0a5553be1d89383cd90d07ebc` |
| `mrt_stations.geojson` | data.gov.sg (LTA) | `d_5cb3563c5584bb533dfc3fbec97153e8` |
| `hospitals.geojson` | data.gov.sg (LTA) Manually curated, Included in repo | `d_1338b55f6d4ea6b2df9884ec4bce4464` | 
| `schools.geojson` | data.gov.sg (MOE) | Search: "General Information of Schools" | `d_688b934f82c1059ed0a6993d2a829089` |
| `parks.geojson` | data.gov.sg (NParks) | Search: "Parks" | `d_0542d48f0991541706b58059381a6eca` |
 `shopping_malls.csv`| Wikipedia | https://en.wikipedia.org/wiki/List_of_shopping_malls_in_Singapore |

Manual downloads: https://data.gov.sg/datasets

---