export function isMoneyKey(key: string) {
  return key !== 'lastValue'
    && /amount|total|vat|received|outstanding|paid|revenue|profit|cost|price|buying|selling|fee|rate|deposit|charge|balance|due/i.test(key)
    && !/date|status|type|note|method|side|value/i.test(key)
}

export function isNumericKey(key: string) {
  return /^(quantity|qty|stockInQty|stockOutQty|damageQty|daysOutstanding|margin|exchangeRate|userCount|permissionCount)$/i.test(key)
}

/** Keys that store calendar dates (no time component preferred). */
export function isDateFieldKey(key: string) {
  return /(^date$|date$)/i.test(key) && !isDateTimeFieldKey(key)
}

/** Keys that store timestamps (date + time). */
export function isDateTimeFieldKey(key: string) {
  return /(At$|startDate|dueDate|returnDate|lastLogin|paidAt|depositDate|meetingDate|completedAt|cancelledAt)/i.test(key)
    || key.toLowerCase().endsWith('datetime')
}
