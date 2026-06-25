# 📦 Inventory Intelligence & Procurement Decision Support System

A full-stack, AI-powered inventory management and analytics platform built with Python and Flask. Upload any CSV/Excel dataset, map your columns, and instantly unlock demand forecasting, ABC classification, procurement ranking, dead stock detection, and executive reporting — all from a clean web dashboard.

---

## 🚀 Features

### 📊 Dashboard
- Real-time KPI cards: total inventory value, item count, class A/B/C breakdown
- ABC Analysis with cumulative value distribution
- Inventory health overview with status indicators
- Region & plant filter controls with instant re-computation
- Matplotlib-generated charts (demand overview, procurement trend, status donut) served as inline base64 images

### 🔮 Demand Forecasting
- Vectorized batch forecasting across all materials simultaneously (NumPy — no per-row sklearn loops)
- Two models per material: **Linear Regression (OLS)** and **Holt's Double Exponential Smoothing**
- Auto model selection per material based on lowest RMSE
- 12-month forward forecast with monthly cost projections
- PEAK / NORMAL / LOW demand status classification
- Executive forecast insights: total procurement cost next quarter and next year
- Per-material forecast chart via `/api/forecast-chart/<material_code>`

### 🧠 Inventory Intelligence
- **EOQ (Economic Order Quantity)** — vectorized across entire dataset
- **Safety Stock** — service-level-based (Z = 1.645, 95%)
- **Reorder Point** — avg monthly demand × lead time + safety stock
- **ABC Classification** — automatic A/B/C bucketing by cumulative annual value (70/20/10 rule)
- Demand standard deviation and holding cost computation per material

### 🔍 Material Intelligence
- Per-material deep-dive panel with health score (0–100)
- Health score factors: demand stability, forecast trend, procurement risk, safety stock adequacy
- Order quantity recommendation with justification
- Procurement cost estimator (next month / quarter / year)
- Demand timeline chart (historical + 12-month forecast)
- Searchable material dropdown (all materials by code + description)

### 🔔 Alerts & Automation (Phase 11)
- Alert priority engine: **CRITICAL / MEDIUM / LOW** classification
- Detects: restock risk, procurement exposure, overstock, demand spikes, high-cost material clusters
- Executive Automation Layer: proactive notification logic, automation status tracking
- In-memory automation log (last 100 events)
- Email alert dispatch via SMTP (configurable via environment variables)
- APScheduler integration: weekly forecast refresh, monthly report generation, automatic alert checks
- Manual trigger via `/api/trigger-alert-check`

### 🗂️ Filters
- Filter by **Plant**, **Region**, and **Time Period** (month/year)
- Filters apply across all modules: dashboard, forecasting, reports, dead stock
- Auto-discovers available filter values from uploaded dataset (no hardcoding)
- Filter insights panel showing how selections affect the dataset

### 📉 Dead Stock Detection
- Flags **Dead Stock** (avg monthly demand ≤ 0.1 units), **Low Movement**, and **Overstock Risk**
- Vectorized classification across entire dataset
- Risk level: CRITICAL / HIGH / MEDIUM
- Per-item recommendation (liquidate, reduce orders, review pricing)
- Smart insights summary panel

### 🏆 Procurement Priority Ranking
- Scores every material on: forecast demand, reorder point urgency, ABC class weight, unit cost, safety stock ratio
- Top 10 ranked materials with status: Critical / High Attention / Monitor Closely / Stable
- Detect top risk materials panel
- Procurement insights narrative

### 📑 Reports & Exports
- **Excel Report** — full inventory analysis with styled workbook (openpyxl): KPI sheet, ABC analysis, full material table with conditional formatting
- **Material Report** — per-material deep-dive Excel export
- **Executive Report** — filtered dashboard snapshot with all active filters applied
- Download endpoints: `/download/report`, `/download/material-report/<code>`, `/download/executive-report`

### ⚙️ Column Mapping
- Upload any CSV or Excel file with any column names
- Interactive column mapping UI maps your column names to logical keys (material code, description, quantity, unit price, lead time, category, plant, region)
- Mapping persisted to `data/column_map.json`
- Works with any industry dataset — spare parts, raw materials, finished goods, MRO

### ⚡ Performance
- **Disk cache** (pickle) keyed on dataset hash — inventory intelligence and forecasting results cached on first run, instant on subsequent loads
- Cache auto-invalidated on dataset upload
- Background thread pre-warms cache on server startup
- Vectorized NumPy math throughout — no Python loops over rows
- Forecasting: **66s → 2.9s first run, ~0.8s cached** for 24,000+ materials

---

## 🛠️ Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| **Python 3.10+** | Core language |
| **Flask 2.3+** | Web framework, routing, templating |
| **Pandas** | Data loading, transformation, filtering, aggregation |
| **NumPy** | Vectorized EOQ, safety stock, OLS forecasting, Holt smoothing |
| **Matplotlib** | Chart generation (base64-encoded PNGs for embedding) |
| **openpyxl** | Styled Excel report export (.xlsx) |
| **APScheduler** | Background job scheduling (weekly/monthly automation) |
| **scikit-learn** | Available for extended model experiments |
| **pickle** | Disk-based computation cache |

### Frontend
| Technology | Purpose |
|---|---|
| **Jinja2** | Server-side HTML templating (Flask built-in) |
| **Tailwind CSS** (CDN) | Utility-first styling, responsive layout |
| **Font Awesome 6** | Icons throughout the UI |
| **Vanilla JS** | Filter controls, AJAX calls, dynamic updates |

### Architecture
| Component | Detail |
|---|---|
| **Modular Python packages** | Each feature is a standalone module in `/modules/` |
| **REST API endpoints** | JSON APIs for alerts, filter options, automation status, forecast charts |
| **Session-based flash messages** | Upload feedback, error handling |
| **Environment-variable config** | SMTP credentials, mail server, alert recipient |

---

## 📁 Project Structure

```
phase11_migrated/
├── app.py                          # Flask app — all routes
├── requirements.txt
├── data/
│   ├── inventory_dataset.csv       # Active dataset (uploaded or sample)
│   ├── column_map.json             # Column mapping config
│   └── cache/                      # Auto-generated pickle cache
├── modules/
│   ├── inventory_intelligence.py   # EOQ, Safety Stock, ROP, ABC
│   ├── forecasting.py              # Vectorized OLS + Holt forecasting + cache
│   ├── filter_engine.py            # Plant / Region / Period filtering
│   ├── material_intelligence.py    # Per-material health score & deep analysis
│   ├── alert_engine.py             # CRITICAL/MEDIUM/LOW alert classification
│   ├── automation_engine.py        # Phase 11 executive automation layer
│   ├── dead_stock_detection.py     # Dead stock / slow-moving / overstock flags
│   ├── procurement_ranking.py      # Priority scoring & ranking
│   ├── chart_generator.py          # Matplotlib chart generation
│   ├── report_export.py            # Excel full-dataset report
│   ├── material_report.py          # Per-material Excel export
│   ├── executive_report.py         # Filtered executive Excel report
│   ├── executive_summary.py        # KPI summary generation
│   ├── email_alerts.py             # SMTP email dispatch
│   └── scheduler.py                # APScheduler job management
└── templates/
    ├── base.html                   # Sidebar layout shell
    ├── index.html                  # Upload & landing page
    ├── dashboard.html              # Main dashboard
    ├── forecast.html               # Forecasting page
    ├── alerts.html                 # Alerts & automation panel
    ├── material_intelligence.html  # Material deep-dive
    └── column_mapping.html         # Column mapper UI
```

---

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.10 or higher
- pip

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/inventory-intelligence-system.git
cd inventory-intelligence-system
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the app
```bash
python app.py
```

Open your browser at **http://localhost:5000**

---

## 📤 Usage

1. **Upload your dataset** — CSV or Excel (.xlsx). Any column names are accepted.
2. **Map columns** — Use the Column Mapping page to link your column names to the system's logical fields (material code, description, quantity, unit price, etc.).
3. **Dashboard** — View KPIs, ABC breakdown, and charts. Apply plant/region/period filters.
4. **Forecast** — See 12-month demand forecasts for every material with model auto-selection.
5. **Alerts** — Review CRITICAL / MEDIUM / LOW alerts. Trigger automation checks manually.
6. **Material Intelligence** — Search any material for a full health score, order recommendation, and procurement cost estimate.
7. **Download Reports** — Export Excel reports (full dataset, per-material, or executive summary).

### Email Alerts (optional)
Set these environment variables before starting the app:
```bash
export MAIL_SERVER=smtp.gmail.com
export MAIL_PORT=587
export MAIL_USERNAME=your@email.com
export MAIL_PASSWORD=yourpassword
export MAIL_DEFAULT_SENDER=your@email.com
export ALERT_RECIPIENT=recipient@email.com
```

---

## 📊 Supported Dataset Formats

The system accepts **any CSV or Excel file** with at minimum:
- A material/item code column
- A description column
- A quantity column
- A unit price/cost column

Optional columns that unlock additional features: Lead Time, Category, Plant, Region.

---

## 🔌 Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/dashboard` | Main dashboard (HTML) |
| `GET` | `/forecast` | Forecast page (HTML) |
| `GET` | `/alerts` | Alerts & automation panel (HTML) |
| `GET` | `/material-intelligence` | Material deep-dive (HTML) |
| `GET` | `/api/alerts` | JSON alert data |
| `GET` | `/api/filter-options` | Available plant/region/period values |
| `GET` | `/api/dashboard-data` | Dashboard KPIs (JSON) |
| `GET` | `/api/forecast-chart/<code>` | Base64 forecast chart for a material |
| `GET` | `/api/material-intelligence/<code>` | Full material analysis (JSON) |
| `GET` | `/api/materials-list` | All material codes + descriptions |
| `GET` | `/api/procurement-ranking` | Top 10 priority materials (JSON) |
| `GET` | `/api/automation-status` | Automation engine status |
| `POST` | `/api/trigger-alert-check` | Manually trigger alert evaluation |
| `POST` | `/api/clear-cache` | Invalidate computation cache |
| `GET` | `/download/report` | Full Excel report download |
| `GET` | `/download/executive-report` | Filtered executive Excel report |
| `GET` | `/download/material-report/<code>` | Per-material Excel report |
| `POST` | `/upload` | Dataset upload |
| `GET` | `/load-sample` | Load built-in sample dataset |

---

## 📈 Performance Benchmarks

Tested on 24,134-material spare parts dataset:

| Operation | Before Optimization | After (First Run) | After (Cached) |
|---|---|---|---|
| Forecasting | 66.2s | 2.9s | 0.8s |
| Inventory Intelligence | 0.78s | 0.06s | 0.03s |
| Dead Stock Detection | 0.85s | 0.25s | 0.25s |
| **Full Page Load** | **~72s** | **~5.6s** | **~3.3s** |

---

## Acknowledgements:

Built with Flask, pandas, NumPy, Matplotlib, openpyxl, APScheduler, Tailwind CSS, and Font Awesome.
for exhaustiveTechStack check file w the same name.
