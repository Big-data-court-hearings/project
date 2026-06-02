# Analytical Database Schema: Court Case Metrics
This document contains the consolidated data dictionary for the Bronze, Silver, and Gold metrics pipelines tracking court case analytics, backlogs, durations, and clearance efficiencies. This data reflects the reference documentation outlined in ACTIVE.pdf.

---

## 1. Case Activity & Volume Metrics

### ACTIVE_CASES_BY_COURT_YEAR[cite: 1]
Tracks active case volume aggregated by court and yearly activity periods.
* **Granularity:** Court + Year[cite: 1]
* **Target Schema:**

| Column Name | Type / Format | Description |
| :--- | :--- | :--- |
| `court_id` | String | Unique identifier for each court.[cite: 1] |
| `circuit` | String | Circuit identifier ($1\text{--}11 + \text{DC} + 20$ for national + fc).[cite: 1] |
| `active_period` | String (YYYY) | Year of activity.[cite: 1] |
| `active_cases_count` | Integer | Total active cases among those filed after 2020 within the period.[cite: 1] |

### ACTIVE_CASES_BY_COURT_QUARTER[cite: 2]
Tracks active case volume aggregated by court and quarterly activity periods.
* **Granularity:** Court + Quarter[cite: 2]
* **Target Schema:**

| Column Name | Type / Format | Description |
| :--- | :--- | :--- |
| `court_id` | String | Unique identifier for each court.[cite: 2] |
| `circuit` | String | Circuit identifier ($1\text{--}11 + \text{DC} + 20$ for national + fc).[cite: 2] |
| `active_period` | String (YYYY-QQ) | Year and quarter of activity.[cite: 2] |
| `active_cases_count` | Integer | Total active cases among those filed after 2020 within the period.[cite: 2] |

### ACTIVE_CASES_BY_COURT
Current snapshot of total active cases per individual court.
* **Granularity:** Court
* **Target Schema:**

| Column Name | Description |
| :--- | :--- |
| `court_id` | Unique identifier for each court. |
| `active_cases_count` | Currently active cases among cases filed after 2020. |

---

## 2. Circuit-Level Aggregations & Temporal Trends

### METRICS_BY_CIRCUIT
High-level summary metrics for each judicial circuit.
* **Granularity:** Circuit
* **Target Schema:**

| Column Name | Description |
| :--- | :--- |
| `circuit` | Circuit identifier ($1\text{--}11 + \text{DC} + 20$ for national + fc). |
| `active_cases_count` | Current active cases among cases filed after 2020. |
| `avg_resolution_days` | Average resolution days calculated for a case. |

### ACTIVE_CASES_BY_CIRCUIT_YEAR
Yearly historical trends of active cases grouped by circuit.
* **Granularity:** Circuit + Year
* **Target Schema:**

| Column Name | Description |
| :--- | :--- |
| `circuit` | Circuit identifier ($1\text{--}11 + \text{DC} + 20$ for national + fc). |
| `active_year` | Year of activity. |
| `active_cases_count` | Total active cases in that specific year. |

### ACTIVE_CASES_BY_CIRCUIT_QUARTER
Quarterly historical trends of active cases grouped by circuit.
* **Granularity:** Circuit + Quarter
* **Target Schema:**

| Column Name | Type / Format | Description |
| :--- | :--- | :--- |
| `circuit` | String | Circuit identifier ($1\text{--}11 + \text{DC} + 20$ for national + fc). |
| `active_quarter` | String (YYYY-QQ) | Year and quarter of activity (e.g., "2023-q1"). |
| `active_cases_count` | Integer | Total active cases in that specific quarter. |

---

## 3. Case Inflow & Outflow Ingestion

### CASE_INFLOW_BY_YEAR / QUARTER
Measures total volumes of newly filed cases.
* **Target Schema:**

| Column Name | Type / Format | Description |
| :--- | :--- | :--- |
| `year_filed` / `year_quarter_filed` | String | Time frame when the case was originally created (e.g., "2023-q1"). |
| `circuit` | String | Circuit identifier ($1\text{--}11 + \text{DC} + 20$ for national + fc). |
| `inflow` / `filed_cases` | Integer | Total number of incoming cases filed in that period. |
| `avg_resolution_days` | Float | Average resolution days within the period. |
| `active_cases` | Integer | Active cases remaining from the cohort filed during this period. |

### CASE_OUTFLOW_BY_YEAR / QUARTER
Measures total volumes of terminated/resolved cases.
* **Target Schema:**

| Column Name | Type / Format | Description |
| :--- | :--- | :--- |
| `year_filed` / `year_quarter_filed` | String | Time frame of case filing/creation (e.g., "2023-q1"). |
| `circuit` | String | Circuit identifier ($1\text{--}11 + \text{DC} + 20$ for national + fc). |
| `inflow` / `terminated_cases` | Integer | Total number of cases terminated/closed in that period. |
| `avg_resolution_days` | Float | Average resolution days for cases *terminated* within this period. |

---

## 4. Case Duration Distribution Analytics
These tables contain statistical distributions (mean, median, standard deviation, and percentiles) for resolved case durations, broken down by termination timeline.

### CASE_DURATION_DISTRIBUTION_CIRCUIT_BY_QUARTER
### CASE_DURATION_DISTRIBUTION_COURT_BY_QUARTER

| Column Name | Type / Format | Description |
| :--- | :--- | :--- |
| `year_quarter_terminated` | String (YYYY-QQ) | Year and quarter when cases were resolved (e.g., "2023-q1"). |
| `court_id` / `circuit` | String | Unique court identifier OR Circuit code ($1\text{--}11 + \text{DC} + 20$). |
| `resolved_cases` | Integer | Volume of cases successfully resolved in that quarter. |
| `mean_duration` | Float | Arithmetic mean of duration for resolved cases. |
| `median_duration` | Float | Median duration of the resolved cases. |
| `std_duration` | Float | Standard deviation of the resolved case durations. |
| `min_duration` | Float | Minimum duration recorded for a resolved case. |
| `max_duration` | Float | Maximum duration recorded for a resolved case. |
| `p75_duration` | Float | 75th percentile (duration of the shortest 75% of resolved cases). |
| `p90_duration` | Float | 90th percentile (duration of the shortest 90% of resolved cases). |

---

## 5. Backlog & Efficiency Profiling

### COURT_BACKLOG_EVOLUTION
Tracks performance and cumulative backlog trends at the court level.

| Column Name | Statistical Formula / Description |
| :--- | :--- |
| `court_id` | Unique identifier for each court. |
| `year_quarter` | Evaluation time period (YYYY-QQ). |
| `inflow_cases` | New incoming cases in the period. |
| `outflow_cases` | Closed/terminated cases in the period. |
| `backlog_clearance_ratio` | $$\frac{\text{Terminated Cases}}{\text{Filed Cases in a Year}}$$ Measures how much courts are falling behind. Needs to be $> 1.0$ ($> 100\%$) for backlogs to decline. |
| `backlog` | **Net Change Accumulation:** Cumulative backlog build-up over the years. (Needs to be decreasing over time). |
| `clearance_efficiency` | $$\frac{\text{Outflow}}{\text{Backlog}}$$ Measures how much of the cumulative backlog is successfully eaten away in the period. |

### CIRCUIT_BACKLOG_EVOLUTION
Tracks overall performance and cumulative backlog trends aggregated up to the circuit level.

| Column Name | Statistical Formula / Description |
| :--- | :--- |
| `circuit` | Circuit identifier ($1\text{--}11 + \text{DC} + 20$). |
| `year_quarter` | Evaluation time period (YYYY-QQ). |
| `inflow` | Total incoming cases. |
| `active_cases` | Total active open cases remaining. |
| `outflow` | Total resolved/terminated cases. |
| `net_change` | $$\text{Inflow} - \text{Outflow}$$ (Can result in a negative value when backlog decreases). |
| `backlog` | **Net Change Accumulation:** Cumulative accumulation over the years. |
| `clearance_efficiency` | $$\frac{\text{Outflow}}{\text{Backlog}}$$ Measures how much of the cumulative backlog is eaten away. |
| `backlog_clearance_ratio` | $$\frac{\text{Terminated Cases}}{\text{Filed Cases}}$$ Measures if the circuit is keeping up with immediate annual incoming pace. |

### CLEARANCE_RATE_CIRCUIT_BY_QUARTER
A simplified monitoring view for immediate quarterly clearance performance.

| Column Name | Statistical Formula / Description |
| :--- | :--- |
| `year_quarter` | Execution quarter. |
| `circuit` | Circuit identifier. |
| `inflow` | Cases filed during the quarter. |
| `outflow` | Cases terminated during the quarter. |
| `backlog_clearance_rate` | $$\frac{\text{Terminated}}{\text{Filed}}$$ |
| `backlog_clearance_rate_pct` | $$\left(\frac{\text{Terminated}}{\text{Filed}}\right) \times 100$$ |