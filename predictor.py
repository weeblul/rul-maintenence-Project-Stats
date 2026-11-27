# Layer 2: the predictor.
# Loads the saved models and returns (rul, risk) for one engine.

import pickle

features = ["s11", "s4", "s17", "s13", "s3", "s2", "s9", "s20", "s21", "s15"]

scaler = pickle.load(open("models/scaler.pkl", "rb"))
rul_model = pickle.load(open("models/rul_model.pkl", "rb"))
risk_model = pickle.load(open("models/risk_model.pkl", "rb"))


def predict(engine_rows):
    # engine_rows = all the rows of one engine up to today
    data = engine_rows[features].copy()

    # same rolling mean as in training (last 5 cycles)
    for s in features:
        data[s] = data[s].rolling(5, min_periods=1).mean()

    # we only need the newest row (today)
    today = data.tail(1)
    X = scaler.transform(today)

    rul = rul_model.predict(X)[0]
    risk = risk_model.predict_proba(X)[0][1]   # chance of failing in the next 30 cycles
    return round(rul, 1), round(risk, 3)
