# Layer 3: the three agents.
# They only talk to the database through erp.py, and every action is written to the audit log.

import erp
from explain import explain

PART = "HPC-01"          # the spare part every alert needs
COST_LIMIT = 50000       # orders above this need a person to approve them
DEFER_WINDOW = 14        # look at low priority jobs in the next 14 days
DEFER_DAYS = 14          # and move them 14 days later


def stock_agent(day, engine, rul, risk):
    stock = erp.get_stock(PART)
    details = ("engine " + engine + " has risk " + str(risk) + " and predicted RUL " + str(rul) +
               " cycles, and there are " + str(stock) + " spare " + PART + " parts in stock")

    if stock >= 1:
        erp.reserve_part(PART)
        erp.add_work_order(engine, "Replace HPC module (part reserved)", "high", day + 2)
        erp.add_log(day, "Stock agent", "Reserved 1 " + PART + " for " + engine,
                    explain("Stock agent", "reserve a spare part", details))
    else:
        erp.add_log(day, "Stock agent", "No stock for " + engine + ", sent to procurement",
                    explain("Stock agent", "pass the job to the procurement agent", details))
        procurement_agent(day, engine, rul)

    # a high priority job was added, so free up time in the schedule
    scheduler_agent(day)


def procurement_agent(day, engine, rul):
    suppliers = erp.get_suppliers(PART)    # sorted from cheapest to most expensive

    # pick the cheapest supplier that can deliver before the engine is expected to fail
    chosen = None
    for supplier in suppliers:
        lead_time = supplier[3]
        if lead_time < rul:
            chosen = supplier
            break
    # if nobody is fast enough, take the fastest one
    if chosen is None:
        chosen = suppliers[0]
        for supplier in suppliers:
            if supplier[3] < chosen[3]:
                chosen = supplier

    supplier_id = chosen[0]
    supplier_name = chosen[1]
    cost = chosen[2]
    lead_time = chosen[3]

    if cost > COST_LIMIT:
        status = "waiting for approval"
    else:
        status = "approved"

    erp.add_requisition(day, engine, PART, supplier_id, 1, cost, status)
    erp.add_work_order(engine, "Replace HPC module (waiting for part)", "high", day + lead_time)

    details = (supplier_name + " was picked with price " + str(cost) + " euro and delivery in " +
               str(lead_time) + " days, the predicted RUL is " + str(rul) + " cycles, and the cost limit is " +
               str(COST_LIMIT) + " euro so the status is '" + status + "'")
    erp.add_log(day, "Procurement agent", "Raised requisition for " + engine + " (" + status + ")",
                explain("Procurement agent", "raise a purchase requisition", details))


def scheduler_agent(day):
    # only LOW priority jobs are moved, high priority jobs are never touched
    orders = erp.get_open_low_priority_orders(day, day + DEFER_WINDOW)
    for order in orders:
        wo_id = order[0]
        engine = order[1]
        old_day = order[2]
        new_day = old_day + DEFER_DAYS
        erp.defer_work_order(wo_id, new_day)
        details = ("a high priority repair was just added and this routine job for " + engine +
                   " was planned for day " + str(old_day) + ", so it moves to day " + str(new_day))
        erp.add_log(day, "Scheduler agent", "Deferred work order " + str(wo_id),
                    explain("Scheduler agent", "defer a low priority work order", details))
