# CourtListener Judicial Analytics Dashboard

Interactive judicial analytics project exploring court activity, backlog dynamics, and judicial performance indicators using CourtListener litigation data.

The project combines Medallion Architecture pipelines, parquet analytical layers, DuckDB processing, analytical visualizations, and an interactive Streamlit dashboard.

---

## Architecture

![Judicial analytics architecture](docs/images/architecture_project.png)

End-to-end Medallion-inspired analytical pipeline for judicial data ingestion, transformation, and KPI generation.

---

## How to run it

Requirements:

- having Docker installed and running,

- having a python 3.12 environment activated and selected as interpreter,

- having a Courtlistener personal token to access the API.

To test the program to its full potential, we recommend running in order the following programs:

- access: https://drive.google.com/drive/folders/1-pogtrR4fofkjftPa86cw_hEXPVQ0G4G?usp=drive_link and follow the instructions in the README file, 

- install the packages in 'requirements.txt' (pip install -r requirements.txt),

- run_kafka.py : it will fetch data from Courtlistener and process it through the Silver layer,

- run_gold_pipeline.py: it will combine the new data with our existing database and compute the gold metrics that will be used for the dashboard,

- dashboard.py : don't run it directly, use in the terminal 'python -m streamlit run "./dashboard.py"'. In case it doesn't work, use the absolute path to the script. It will launch a dashboard with the most important metrics for cases backlogs

- predict_resolution.py : taking a parquet file of unresolved cases as input, it predicts the expected case duration for each of the records in the file,

- check_status.py : it checks whether a case, identified by its docket number, has been terminated or not


---

## Dashboard preview

![Dashboard preview](docs/images/dashboard_preview.png)

Interactive Streamlit dashboard for backlog monitoring, court performance analysis, clearance-rate exploration, and judicial duration analytics.

---

## Presentation

Full presentation available in:

[BDT Project Presentation](docs/presentation/BDT_Project_Presentation.pptx)

---

## Project objectives

This project investigates judicial workload and court congestion dynamics through exploratory analytical metrics derived from CourtListener public litigation records.

The analysis focuses on:
- judicial backlog evolution,
- case inflow and outflow dynamics,
- clearance rate estimation,
- court-level workload disparities,
- case duration distributions,
- exploratory judicial performance indicators.

The project aims to:
- build a reproducible judicial analytics pipeline,
- implement a Medallion Architecture workflow,
- generate analytical parquet datasets,
- support exploratory court performance analysis,
- provide an interactive dashboard for visual analytics.

---

## Medallion Architecture

The project follows a layered analytical architecture:

```text
CourtListener API
        ↓
Bronze Layer
(raw ingestion using Kafka Producer)
        ↓
Silver Layer
(Consumer receives, cleans and stores docket datasets)
        ↓
Gold Pipelines
(KPI generation)
        ↓
Gold Metrics
(analytical parquet tables)
        ↓
DuckDB + Streamlit Dashboard
```

The architecture separates:
- raw ingestion,
- cleaned datasets,
- analytical metrics,
- dashboard serving and visualization layers.

---

## Current dataset status

Current exploratory dataset:

- ~34k judicial records
- Filing date coverage: 1985–2026 (strongly concentrated after 2020)
- Active cases: ~33k
- Resolved cases: ~800
- Average observed duration: ~148 days
- Incremental checkpoint-based ingestion
- Historical time-window ingestion support
- Append-only Bronze architecture

The dataset remains exploratory and partially incomplete due to API coverage limitations and right-censoring effects.

---

## Methodological overview

The analytical pipeline combines:
- CourtListener litigation data,
- parquet-based storage layers,
- DuckDB analytical processing,
- Streamlit interactive visualization.

The project remains exploratory and observational:
- no causal inference is claimed,
- judicial coverage remains incomplete,
- terminated case coverage remains limited,
- several metrics remain sensitive to right-censoring effects.

The current dataset exhibits:
- strong imbalance between active and resolved cases,
- backlog accumulation,
- heterogeneous court activity levels,
- sparse duration observations.

---

## Project structure

```text
project/
│
├── data/
│   └── dockets_terminated_25_onwards.jsonl
│
├── dashboard/
│   ├── pages/
│   └── app.py
│
├── docs/
│   ├── presentation/BDT_Project_Presentation.pptx
│   ├── report/
│   ├── dashboard_preview.png
│   └── images/
│       ├── architecture_project.png
│       └── dashboard_preview.png
│
├── logs/
│
├── gold/
│   ├── metrics/
│   │   ├── active_cases_by_court.parquet
│   │   ├── avg_resolution_time_by_court.parquet
│   │   ├── backlog_by_year.parquet
│   │   ├── case_duration_distribution.parquet
│   │   ├── case_inflow_by_year.parquet
│   │   ├── case_metrics.parquet
│   │   ├── case_outflow_by_year.parquet
│   │   ├── clearance_rate_by_year.parquet
│   │   └── court_performance_metrics.parquet
│   │
│   └── pipelines/
│       ├── build_backlog_metrics.py
│       ├── build_case_metrics.py
│       ├── build_clearance_rate.py
│       ├── build_court_performance.py
│       ├── build_duration_metrics.py
│       ├── build_metrics.py
│       └── build_temporal_metrics.py
│
├── ingestion/
│   ├── api_client.py
│   ├── checkpoint.py
│   ├── config.py
│   └── kafkaProducer.py
│
├── scripts/
│   └── run_historical_ingest.py
│
├── silver/
|
|__ run_pipeline.py
|
├── README.md
├── requirements.txt
├── .gitignore
└── Dockerfile
```

---

## Analytical workflow

### 01 — Data ingestion

- CourtListener API requests
- paginated ingestion,
- raw docket collection,
- Kafka Producer sending raw dockets to the bronze topic


### 02 — Silver processing

- Kafka Consumer reception of raw dockets
- docket cleaning,
- schema harmonisation,
- temporal normalization,
- cleaned parquets generation.

### 03 — Gold analytical pipelines

- case metrics construction,
- inflow and outflow aggregation,
- backlog computation,
- clearance rate estimation,
- duration analytics,
- court-level KPI generation.

### 04 — Dashboard analytics

- judicial KPI overview,
- backlog evolution visualization,
- court congestion rankings,
- duration distribution analysis,
- interactive KPI exploration.

---

## Gold analytical metrics

The Gold layer generates several analytical KPI datasets.

### Judicial backlog

The backlog metric is estimated as cumulative inflow minus cumulative outflow over time.

```text
Backlog(t) =
Σ Inflow(i) − Σ Outflow(i)
for i ≤ t
```

### Clearance rate

The clearance rate is defined as:

```text
CR(t) = Outflow(t) / Inflow(t)
```

### Case duration

Case duration is computed as the time difference between filing and termination dates.

```text
Duration = date_terminated − date_filed
```

---

## Streamlit Dashboard Features

The interactive dashboard includes:

- judicial KPI overview,
- backlog evolution analytics,
- inflow vs outflow visualization,
- court congestion rankings,
- case duration distributions,
- clearance rate analysis,
- interactive parquet table exploration.

---

### Incremental ingestion update

```bash
python ingestion/ingest_dockets.py
```

### Historical ingestion

```bash
python scripts/run_historical_ingest.py --start-date 2020-01-01 --end-date 2025-12-31 --window year --use-disk-index
```

---

### Rebuild analytical layers

```bash
python silver/clean_dockets.py

python gold/run_gold_pipeline.py

python gold/pipelines/build_advanced_metrics.py
```

---

### Clone the Repository

```bash
git clone https://github.com/Big-data-court-hearings/project.git
cd project
```

### Create and Activate a Virtual Environment

```bash
python -m venv .venv
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Launch the Dashboard

```bash
streamlit run dashboard/app.py
```

---

## Docker

### Build container

```bash
docker build -t judicial-dashboard .
```

### Run container

```bash
docker run -p 8501:8501 judicial-dashboard
```

### Access dashboard

```text
http://localhost:8501
```

## Main analytical observations

Current exploratory findings include:

- strong imbalance between active and resolved cases,
- significant backlog accumulation,
- low observed clearance rates in recent years,
- heterogeneous court-level duration patterns,
- sparse termination observations across jurisdictions.

The current analytical results should be interpreted cautiously due to:
- exploratory dataset size,
- incomplete temporal coverage,
- strong right-censoring effects.

Additional limitations include:

- incomplete historical coverage,
- heterogeneous court representation,
- temporal imbalance toward recent active cases,
- sparse termination observations,
- API/network instability during large historical ingestion runs.

---

## Scalability and engineering design

The platform was designed to support scalable judicial analytics workflows.

Implemented engineering features include:

- incremental ingestion,
- append-only Bronze storage,
- checkpoint-based updates,
- historical time-window ingestion,
- parquet analytical layers,
- DuckDB analytical querying,
- modular Gold KPI pipelines,
- interactive Streamlit analytics.

The architecture separates ingestion, cleaning, analytical computation, and visualization layers in order to improve reproducibility and extensibility.

---

## Future work

Potential future improvements include:

- larger-scale historical ingestion,
- automated scheduled incremental updates,
- advanced backlog forecasting,
- court clustering and anomaly detection,
- additional judicial workload and resolution indicators,
- deployment on cloud analytical infrastructure.

---

## Technologies Used

- Python
- pandas
- DuckDB
- Plotly
- Streamlit
- parquet
- Jupyter Notebook

---

## GitHub Repository

https://github.com/Big-data-court-hearings/project.git

---

## Team And Collaboration

The project was developed collaboratively as part of the Big Data Technologies course at the University of Trento.

Main collaborative activities included:
- judicial analytics pipeline design,
- CourtListener ingestion architecture,
- analytical KPI generation,
- dashboard development,
- project documentation and presentation.

## Authors

Asia Panizza  
MSc Data Science — University of Trento

Yasmin El Morady  
MSc Data Science — University of Trento

Henri Vasserot  
MSc Data Science — University of Trento