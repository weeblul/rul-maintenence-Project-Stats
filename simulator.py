# Layer 2: the simulator.
# It pretends a small fleet of engines is flying. 1 cycle = 1 day.
# Every day each engine gets one more row of sensor data from the NASA test file.

import pandas as pd

column_names = ["unit", "cycle", "op1", "op2", "op3"]
for i in range(1, 22):
    column_names.append("s" + str(i))


def load_fleet(number_of_engines=10):
    # load the FD001 test engines
    test = pd.read_csv("data/test_FD001.txt", sep=r"\s+", header=None, names=column_names)
    test["engine"] = "FD001_" + test["unit"].astype(str)

    # true RUL at the end of each test engine (from NASA)
    true_rul = pd.read_csv("data/RUL_FD001.txt", header=None, names=["true_RUL"])
    true_rul["engine"] = "FD001_" + (true_rul.index + 1).astype(str)

    # pick the engines closest to failure so the demo shows some alerts
    chosen = true_rul.sort_values("true_RUL").head(number_of_engines)["engine"].tolist()

    fleet = test[test["engine"].isin(chosen)]
    return fleet, chosen


def data_until_day(fleet, engine, day):
    # all the rows for one engine from cycle 1 up to today
    one_engine = fleet[fleet["engine"] == engine]
    return one_engine[one_engine["cycle"] <= day]


def last_day(fleet):
    # the simulation runs until the longest engine runs out of data
    return fleet["cycle"].max()
