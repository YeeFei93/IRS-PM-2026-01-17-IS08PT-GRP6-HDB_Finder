# RS-PM-2026-01-17-IS08PT-GRP-HDB

## HDB Estate Recommender — Singapore

A React + Tailwind CSS web app that recommends HDB resale estates based on your buyer profile, budget, and amenity preferences. It pulls live resale transaction data from [data.gov.sg](https://data.gov.sg), computes applicable grants (EHG, CPF Housing Grant, PHG), and scores/ranks estates across budget fit, transport access, amenities, and region match.

## Prerequisites

- [Node.js](https://nodejs.org/) v18 or later
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