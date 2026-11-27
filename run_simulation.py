# Runs layers 2 and 3 together.
# Every day: get new sensor data -> predict (rul, risk) -> if risk >= 0.7 the agents act.
# The notebook calls run_simulation() after it has saved the models and made the database.

import erp
import simulator
import predictor
import agents

RISK_THRESHOLD = 0.7


def run_simulation():
    fleet, engines = simulator.load_fleet(number_of_engines=10)
    print("Engines in the fleet:", engines)

    already_alerted = []   # so the agents only act once per engine

    for day in range(1, simulator.last_day(fleet) + 1):
        for engine in engines:
            rows = simulator.data_until_day(fleet, engine, day)

            # skip engines with no new data today (they ran out of data)
            if len(rows) == 0 or rows["cycle"].max() < day:
                continue

            rul, risk = predictor.predict(rows)
            erp.save_prediction(day, engine, rul, risk)

            # the trigger
            if risk >= RISK_THRESHOLD and engine not in already_alerted:
                print("Day", day, "-", engine, "risk", risk, "RUL", rul, "-> agents act")
                already_alerted.append(engine)
                agents.stock_agent(day, engine, rul, risk)

    print()
    print("Simulation finished after", simulator.last_day(fleet), "days")
    print("Engines that raised an alert:", len(already_alerted), "of", len(engines))


# this part only runs when you type "python run_simulation.py" yourself (not when the notebook imports it)
if __name__ == "__main__":
    erp.create_database()
    run_simulation()
    print("Now run:  python app.py")
