def tip(bill, rate=0.15):
    return round(bill * rate, 2)


def split(total, people):
    # Bug for the demo: integer division drops the cents.
    return total // people


def total_with_tip(bill, rate=0.15):
    return round(bill + tip(bill, rate), 2)
