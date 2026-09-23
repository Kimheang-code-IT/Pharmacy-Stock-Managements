import type { FieldOption } from '~/types/stock-pos/common'

/** Shared select options for settings / forms with fixed choice lists. */

export const TIMEZONE_OPTIONS: FieldOption[] = [
  { label: 'Asia/Phnom_Penh (Cambodia)', value: 'Asia/Phnom_Penh' },
  { label: 'Asia/Bangkok (Thailand)', value: 'Asia/Bangkok' },
  { label: 'Asia/Ho_Chi_Minh (Vietnam)', value: 'Asia/Ho_Chi_Minh' },
  { label: 'Asia/Singapore', value: 'Asia/Singapore' },
  { label: 'Asia/Jakarta', value: 'Asia/Jakarta' },
  { label: 'Asia/Kuala_Lumpur', value: 'Asia/Kuala_Lumpur' },
  { label: 'Asia/Manila', value: 'Asia/Manila' },
  { label: 'Asia/Tokyo', value: 'Asia/Tokyo' },
  { label: 'Asia/Seoul', value: 'Asia/Seoul' },
  { label: 'Asia/Shanghai', value: 'Asia/Shanghai' },
  { label: 'Asia/Hong_Kong', value: 'Asia/Hong_Kong' },
  { label: 'Asia/Dubai', value: 'Asia/Dubai' },
  { label: 'Asia/Kolkata', value: 'Asia/Kolkata' },
  { label: 'Europe/London', value: 'Europe/London' },
  { label: 'Europe/Paris', value: 'Europe/Paris' },
  { label: 'America/New_York', value: 'America/New_York' },
  { label: 'America/Los_Angeles', value: 'America/Los_Angeles' },
  { label: 'UTC', value: 'UTC' },
]

export const DATE_FORMAT_OPTIONS: FieldOption[] = [
  { label: 'YYYY-MM-DD', value: 'YYYY-MM-DD' },
  { label: 'DD/MM/YYYY', value: 'DD/MM/YYYY' },
  { label: 'MM/DD/YYYY', value: 'MM/DD/YYYY' },
  { label: 'DD-MM-YYYY', value: 'DD-MM-YYYY' },
  { label: 'D MMM YYYY', value: 'D MMM YYYY' },
]

export const TIME_FORMAT_OPTIONS: FieldOption[] = [
  { label: '24-hour (HH:mm)', value: 'HH:mm' },
  { label: '24-hour with seconds (HH:mm:ss)', value: 'HH:mm:ss' },
  { label: '12-hour (h:mm A)', value: 'h:mm A' },
  { label: '12-hour with seconds (h:mm:ss A)', value: 'h:mm:ss A' },
]

export const NUMBER_FORMAT_OPTIONS: FieldOption[] = [
  { label: '1,234.56', value: '1,234.56' },
  { label: '1.234,56', value: '1.234,56' },
  { label: '1 234,56', value: '1 234,56' },
]

export const CURRENCY_OPTIONS: FieldOption[] = [
  { label: 'USD — US Dollar', value: 'USD' },
  { label: 'KHR — Cambodian Riel', value: 'KHR' },
]

export const PAGE_SIZE_OPTIONS: FieldOption[] = [
  { label: '10', value: '10' },
  { label: '20', value: '20' },
  { label: '25', value: '25' },
  { label: '50', value: '50' },
  { label: '100', value: '100' },
]

export const LANDING_PAGE_OPTIONS: FieldOption[] = [
  { label: 'Dashboard', value: '/' },
  { label: 'Categories', value: '/setup/categories' },
  { label: 'Stock', value: '/stock/products' },
  { label: 'Suppliers', value: '/setup/suppliers' },
  { label: 'POS', value: '/pos' },
  { label: 'Customers', value: '/setup/customers' },
  { label: 'Sales Report', value: '/reports/sales' },
]
