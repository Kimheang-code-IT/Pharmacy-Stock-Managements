from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal("0.01")


def money(value) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def clamp_non_negative(value) -> Decimal:
    return max(money(value), Decimal("0.00"))


def allocate_payment(line_totals: list[Decimal], paid_amount) -> list[Decimal]:
    total = sum(line_totals, Decimal("0"))
    paid = clamp_non_negative(paid_amount)
    if total <= 0 or paid <= 0 or not line_totals:
        return [Decimal("0.00") for _ in line_totals]
    capped = min(paid, total)
    shares = []
    for index, line in enumerate(line_totals):
        if index == len(line_totals) - 1:
            continue
        shares.append(money(capped * line / total))
    allocated = sum(shares, Decimal("0"))
    shares.append(money(capped - allocated))
    return shares


def distribute_document_discount(line_totals: list[Decimal], document_discount) -> list[Decimal]:
    total = sum(line_totals, Decimal("0"))
    discount = clamp_non_negative(document_discount)
    if total <= 0 or discount <= 0 or not line_totals:
        return [Decimal("0.00") for _ in line_totals]
    discount = min(discount, total)
    shares = []
    for index, line in enumerate(line_totals):
        if index == len(line_totals) - 1:
            continue
        shares.append(money(discount * line / total))
    allocated = sum(shares, Decimal("0"))
    shares.append(money(discount - allocated))
    return shares
