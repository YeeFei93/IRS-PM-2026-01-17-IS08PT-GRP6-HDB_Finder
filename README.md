## SECTION 1 : PROJECT TITLE
## HDB Finder

<img src="Miscellaneous/Application1.png"
     style="float: left; margin-right: 0px;" />

---

## SECTION 2 : EXECUTIVE SUMMARY / PAPER ABSTRACT

Buying a first home in Singapore should be a milestone, yet it often becomes a tedious, bureaucratic process. With complicated HDB schemes and thousands of HDB resale flats on the market, finding the right estate and property - balancing lifestyle, location, and budget - remains a tiresome and time-consuming process. Currently, no single buyer-focused intelligent system exists to guide buyers through this fragmented landscape.

Our team set out to build **HDB Finder**, an AI-powered HDB recommender system that simplifies property hunting by integrating eligibility rules, HDB grants, property features, and lifestyle preferences into a single, intuitive platform. The system targets Singapore Citizens and Permanent Residents purchasing HDB resale flats, and covers grant eligibility (citizenship, income ceiling, flat ownership rules, HDB and loan schemes) as well as amenity proximity scoring across MRT stations, schools, hawker centres, parks, and hospitals.

The solution is built around a hybrid intelligent reasoning pipeline. A rule-based eligibility engine validates buyer profiles against current HDB policy constraints in real time, computing applicable grants (EHG, CPF Housing Grant, PHG) and an effective budget. A hybrid constraint-based and content-based filtering recommender system then scores and ranks individual resale flat listings using weighted cosine similarity between buyer preference vectors and per-flat feature vectors - covering floor preference, budget fit, and six amenity proximity dimensions - with Maximal Marginal Relevance (MMR) applied for diversity reranking to ensure estate variety in the Top-10 recommendations. To rigorously evaluate recommendation quality, the system conducts A/B testing across three model variants: Weighted Cosine Similarity + MMR, Euclidean Distance, and K-Nearest Neighbours (KNN), enabling objective comparison of ranking performance across different similarity metrics.

All data is sourced from publicly available and authorised datasets: HDB resale transaction records (Oct 2025–present) from data.gov.sg, geospatial amenity data for MRT stations, schools, hawker centres, parks, and hospitals via OneMap and data.gov.sg, and shopping mall data scraped from Wikipedia. The system is delivered as an interactive React web application with a Leaflet map interface, enabling users to visualise flat locations, nearby amenities, and transport links alongside ranked recommendations.

Our team had an enriching experience building this end-to-end AI system, and we hope it empowers first-time HDB buyers to make confident, well-informed housing decisions - reducing complexity at every step of the process.

---

## SECTION 3 : CREDITS / PROJECT CONTRIBUTION

| Official Full Name | Student ID (MTech Applicable) | Work Items (Who Did What) | Email (Optional) |
| :------------ |:---------------:| :-----| :-----|
| Loh Kian Chee (Group Lead) | A0339775J |  Project Ideation, Scope & Management; Frontend User Panel; Frontend App; Eligibility Engine; User Testings & Feedback Collection | kian.chee.loh@u.nus.edu |
| Udayakumar Nivetha | A0245895L | Backend Redis Setup; Euclidean Distance & KNN Cosine Similarity Recommender Models; Models Evaluation Code; User Favorite Tab + Like Functionality; Data Collection (Schools + Hospitals)  | e0908182@u.nus.edu |
| Sim Yee Fei | A0339751W | Frontend (React/Tailwind/Leaflet) UI/UX, 3-phase map drill-down; Frontend Backend data integration (flat-lookup & flat-amenities routes); Weighted Cosine Similarity + MMR Recommender Model; Parallel/cached amenity queries | yee-fei.sim@u.nus.edu |
| Lim Zheng Tao | A0339804X | Data Collection & Preparation; Amenities Relationships & Proximity Distance Conversion; UI/UX Enhancements | zhengtao.lim@u.nus.edu |

---

## SECTION 4 : VIDEO OF SYSTEM MODELLING & USE CASE DEMO

[![HDB Finder Demo](http://img.youtube.com/vi/g_iaRn5MaV0/0.jpg)](https://youtu.be/g_iaRn5MaV0 "HDB Finder")

---

## SECTION 5 : USER GUIDE

`Refer to appendix <Installation & User Guide> in project report at Github Folder: ProjectReport`

### Prerequisites

- [Node.js](https://nodejs.org/) v18 or later (npm included)
- [Python](https://www.python.org/) v3.14.2 
- [MySQL](https://dev.mysql.com/downloads/) v8.0 or later
- [Redis](https://redis.io/) v7 or later (macOS: `brew install redis`)

### [ 1 ] Database Setup

Download and import the pre-built MySQL database dump:

> Download MySQL dump from: https://drive.google.com/file/d/10XaZlv54KmUj2S-HaojwwqJawig5pG0E/view?usp=sharing

```bash
mysql -u root -p < SystemCode/db/iss-irs-ai-estate-recommender-08.sql
```

### [ 2 ] To run the system on macOS / Linux

```bash
cd SystemCode
chmod +x start-dev.sh
./start-dev.sh
```

The script automatically installs all dependencies, starts Redis and MySQL, and launches the backend and frontend.

**Go to URL using web browser:** http://localhost:5173

### [ 3 ] To run the system on Windows

```bat
cd SystemCode
start-dev.bat
```

**Go to URL using web browser:** http://localhost:5173

### [ 4 ] Service Ports

| Service | Port | Description |
|---------|------|-------------|
| Frontend (React/Vite) | 5173 | User-facing web application |
| Backend API (Node.js) | 3000 | REST API gateway |
| Redis | 6379 | Message queue and cache |
| MySQL | 3306 | Primary database |

---

## SECTION 6 : PROJECT REPORT

`Refer to project report at Github Folder: ProjectReport`

**Project Report Sections:**
- Section 1: Business Case 
  - 1.1 Executive Summary	
  - 1.2 Project Background	
  - 1.3 Market Overview and Landscape	
    - 1.3.1 Analysis of HDB Resale Market	
    - 1.3.2 Analysis of Real Estate Agents and Agencies	
    - 1.3.3 Market Size and Value Capture	
    - 1.3.4 Key Players and Competitors	
    - 1.3.5 Market Demands, User Needs and Opportunities	
  - 1.4 Project Scope & Intelligent Reasoning System	
    - 1.4.1 Project Scope	
    - 1.4.2 Intelligent Reasoning System	
- Section 2: System Design	
  - 2.1 Architecture Diagram	
  - 2.2 Service Modules Details	
- Section 3: System Development & Implementation	
  - 3.1 Data Collection and Preparation	
    - 3.1.1 Sources of Data	
    - 3.1.2 How Data is Acquired and Processed	
  - 3.2 HDB Recommender	
    - 3.2.1 Frontend	
    - 3.2.2 Backend Gateway	
    - 3.2.3 Python Micro-services	
    - 3.2.4 Database	
    - 3.2.5 End-to-End Recommendation Flow	
    - 3.2.6 User Interface Features	
- Section 4: Models, Findings and Discussion	
  - 4.1 Recommender Models Implementation	
    - 4.1.1 System & Model Inputs	
    - 4.1.2 Euclidean Distance Model	
    - 4.1.3 KNN Cosine Similarity Model	
    - 4.1.4 Weighted Cosine Similarity + MMR	
    - 4.1.5 Sample Calculations	
  - 4.2 Model Evaluation	
  - 4.3 Challenges Faced	
  - 4.4 Future Improvements
    - 4.4.1 Advanced Recommender Model	
    - 4.4.2 Enhance Amenity Coverage & Travel Time Mapping	
    - 4.4.3 Conversational UI: Interactive AI Chatbot	
    - 4.4.4 Property Appreciation & Asset Valuation	
    - 4.4.5 Interactive Decision Support with 3D Representations	
    - 4.4.6 Ecosystem Expansion	
    - 4.4.7 Other Policy Guidelines	
- Acknowledgement (Use of AI)	
- References (APA7 Format)	
- Appendix	

---

## SECTION 7 : MISCELLANEOUS

### System Architecture

The system follows a microservices architecture:

| Layer | Technology | Description |
|-------|-----------|-------------|
| Frontend | React 19, Vite, Tailwind CSS, Leaflet | Interactive web app with map view |
| Backend API | Node.js, Express, TypeScript | REST API gateway with Redis caching |
| Eligibility Checker Service | Python | Rule-based HDB policy engine |
| Budget Estimator Service | Python | Grant computation (EHG, CPF, PHG) and effective budget |
| Estate Finder Service | Python | Constraint-based flat filtering by region, flat type, budget |
| Recommendation Scorer Service | Python | Weighted Cosine Similarity + MMR, Euclidean Distance and KNN Cosine Similarity (A/B testing evaluation) |
| Amenity Proximity Service | Python | Geospatial distance computation to MRT, schools, hawker centres, parks, hospitals |
| Data Service | Python | Data ingestion pipeline from data.gov.sg APIs |
| Database | MySQL | Resale flat transactions, amenity data, user favourites |
| Cache / Queue | Redis | Adapter result caching and inter-service messaging |

### Data Sources

| Dataset | Source | Link |
|---------|--------|-------|
| Resale Flat Prices By HDB | data.gov.sg | `https://data.gov.sg/datasets?resultId=d_8b84c4ee58e3cfc0ece0d773c8ca6abc` |
| MRT Stations By LTA| data.gov.sg | `https://data.gov.sg/datasets?resultId=d_b39d3a0871985372d7e1637193335da5` |
| MRT Stations Lines By LTA| data.gov.sg | `https://data.gov.sg/datasets?resultId=d_d312a5b127e1ae74299b8ae664cedd4e` |
| Hawker Centres By NEA | data.gov.sg | `https://data.gov.sg/datasets?query=hawker+centres&resultId=d_4a086da0a5553be1d89383cd90d07ecd` |
| Public Sector Hospitals By MOH | data.gov.sg | `https://data.gov.sg/datasets?resultId=d_1338b55f6d4ea6b2df9884ec4bce4464` |
| Schools By MOE | data.gov.sg | `https://data.gov.sg/datasets?resultId=d_688b934f82c1059ed0a6993d2a829089` |
| Parks By NPARKS | data.gov.sg | `https://data.gov.sg/datasets?resultId=d_0542d48f0991541706b58059381a6eca` |
| Planning Area Boundaries By URA | data.gov.sg | `https://data.gov.sg/datasets?resultId=d_4765db0e87b9c86336792efe8a1f7a66` |
| Shopping Malls | Wikipedia | `https://en.wikipedia.org/wiki/List_of_shopping_malls_in_Singapore` |

### External Api Sources
| Source | Link |
|--------|------|
| OneMap Geolocation | `https://www.onemap.gov.sg/api/common/elastic/search`|
| Nominatim OpenStreetMap Geolocation | `https://nominatim.openstreetmap.org/search?q={{address}}&format=jsonv2`|

### Recommendation Scoring — Vector Design

Our recommender adopts a **hybrid rule-based and content-based design**. A rule-based layer first applies hard filters for budget, flat type, eligibility, and region. The remaining eligible flats are then scored using one of three content-based models, selected with equal 1/3 probability: **Euclidean Distance**, **KNN Cosine Similarity**, or **Weighted Cosine Similarity + MMR**.

Each model uses buyer and flat vectors across **7 preference dimensions**: floor preference, MRT proximity, hawker centre proximity, shopping mall proximity, park proximity, primary school proximity, and hospital proximity. Budget and flat type are kept as hard filters rather than vector dimensions to avoid penalising favourable conditions such as lower price or better eligibility fit.

To evaluate and compare recommender performance, the system implements **A/B testing** with 20+ Users (Singles, Married Couple with Families, Downsizers) across three model variants:

| Model | Description |
|-------|-------------|
| Weighted Cosine Similarity + MMR | Preference-weighted angular similarity with diversity reranking |
| Euclidean Distance | Recommends flats closest to the buyer’s preference vector by converting smaller distance into higher similarity scores. |
| K-Nearest Neighbours (KNN) Cosine Similarity | Recommends flats based on both buyer similarity and similarity to nearby candidate flats. |

---
