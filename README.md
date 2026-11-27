# Predicting jet engine Remaining Useful Life + a small maintenance ERP

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/weeblul/rul-maintenence-Project-Stats/blob/main/RUL_project.ipynb)

We use NASA's C-MAPSS engine data (FD001 and FD003) to predict how many cycles an engine has left
before it fails (RUL), and whether it will fail in the next 30 cycles. The models then feed a small
pretend maintenance system: a simulator, three agents, an ERP database and a web dashboard where a
reviewer approves invoices.

| Model | FD001 RMSE | FD003 RMSE |
|---|---|---|
| Mean baseline | 43.08 | 42.50 |
| Linear regression | 21.12 | 21.09 |
| Decision tree (depth 9) | 18.29 | 19.95 |

Logistic regression (fail within 30 cycles): precision 0.81, recall 0.61.

## How it works

```
RUL_project.ipynb  ->  models/  ->  run_simulation.py  ->  agents.py  ->  erp.py (erp.db)  ->  app.py + dashboard.html
  EDA + 4 models       saved       10 engines, 1 day     stock,          SQLite ERP           dashboard, invoices
  + evaluation         models      per cycle, risk>=0.7  procurement,                         approve -> post -> print
                                                         scheduler
```

1. The notebook trains the models, evaluates them and saves them in `models/`.
2. It stores the 200 test predictions in the ERP and runs the simulation. When an engine's risk reaches 0.7
   the agents reserve a part or order one, and move routine jobs.
3. When a purchase is approved (automatically, or by a person if it costs more than 50,000 euro) the supplier
   invoice arrives in the ERP as **pending**.
4. In the dashboard a reviewer clicks **Approve and post**. The ERP marks the invoice **posted** and the invoice
   opens in a new tab, ready to print or save as PDF.

## Run it in Google Colab

1. Click the **Open in Colab** badge above.
2. The first code cell already points `GITHUB_URL` at this repository.
3. Click **Runtime > Run all**. When the upload cell asks, choose the 6 data files (or `CMAPSSData.zip`)
   from your computer. See `data/README.txt` for where to download them.
4. At the end, click **Open the dashboard in a new tab**. If your browser blocks it, copy the printed backup link.

## Run it on your own computer

```
pip install -r requirements.txt
```

1. Put the 6 data files in the `data` folder.
2. Open `RUL_project.ipynb` in Jupyter and run all cells (the last cell starts the dashboard).
3. Or, after running the notebook once, start the dashboard yourself with `python app.py`
   and open http://127.0.0.1:5000.

`python run_simulation.py` runs only the simulation again (it needs the models from the notebook).

## Files

| File | What it does |
|---|---|
| `RUL_project.ipynb` | Data loading, EDA, preprocessing, the 4 models, evaluation, error analysis, then the ERP and dashboard steps |
| `simulator.py` | Plays the 10 FD001 test engines closest to failure, 1 cycle = 1 day |
| `predictor.py` | Loads the saved models and returns `(rul, risk)` for one engine |
| `run_simulation.py` | The daily loop and the trigger (risk >= 0.7, once per engine) |
| `agents.py` | Stock agent, procurement agent and scheduler agent |
| `erp.py` | The ERP: SQLite database `erp.db` with inventory, suppliers, requisitions, work orders, predictions, audit log and invoices. Every other file goes through this file |
| `app.py` | Small Flask web server that gives the dashboard its data and shows the printable invoices |
| `dashboard.html` | The dashboard: maintenance queue, invoices (pending / posted) and requisitions waiting for approval |
| `figures/` | All plots from the notebook |

The dashboard and simulator use the same `erp.db` file beside `erp.py`, regardless of the folder
from which you start them. The dashboard shows whether the database is connected and initialized;
run the notebook to create the ERP tables and populate model predictions before using the live data.

## Made-up demo data

The stock (3 spare modules), the two suppliers and their prices, the routine work orders and the invoices
are invented for the demo. They are set in `create_database()` in `erp.py`.

## Data and licence

NASA C-MAPSS turbofan engine degradation data (Saxena et al., 2008), from the NASA Prognostics Center of
Excellence data repository. NASA lists no specific licence and asks users to cite the dataset. The data is
simulated and has no personal information. The data files are not included here; see `data/README.txt`.

## Team

Daksh Jadhav, Abdul Gaffar Nagori, Jamie McGillicuddy and Rajesh Yadav

