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

export const FIRST_DAY_OF_WEEK_OPTIONS: FieldOption[] = [
  { label: 'Sunday', value: '0' },
  { label: 'Monday', value: '1' },
  { label: 'Saturday', value: '6' },
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

export const LOCALE_OPTIONS: FieldOption[] = [
  { label: 'English (United States)', value: 'en-US' },
  { label: 'English (United Kingdom)', value: 'en-GB' },
  { label: 'Khmer (Cambodia)', value: 'km-KH' },
  { label: 'Thai (Thailand)', value: 'th-TH' },
  { label: 'Vietnamese (Vietnam)', value: 'vi-VN' },
  { label: 'French (France)', value: 'fr-FR' },
  { label: 'Japanese (Japan)', value: 'ja-JP' },
  { label: 'Chinese (Simplified)', value: 'zh-CN' },
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
  { label: 'Stock', value: '/stock' },
  { label: 'Suppliers', value: '/setup/suppliers' },
  { label: 'POS', value: '/pos' },
  { label: 'Customers', value: '/setup/customers' },
  { label: 'Sales Report', value: '/reports/sales' },
]

export const AWS_REGION_OPTIONS: FieldOption[] = [
  { label: 'Asia Pacific (Singapore) ap-southeast-1', value: 'ap-southeast-1' },
  { label: 'Asia Pacific (Jakarta) ap-southeast-3', value: 'ap-southeast-3' },
  { label: 'Asia Pacific (Tokyo) ap-northeast-1', value: 'ap-northeast-1' },
  { label: 'Asia Pacific (Seoul) ap-northeast-2', value: 'ap-northeast-2' },
  { label: 'Asia Pacific (Hong Kong) ap-east-1', value: 'ap-east-1' },
  { label: 'Asia Pacific (Mumbai) ap-south-1', value: 'ap-south-1' },
  { label: 'US East (N. Virginia) us-east-1', value: 'us-east-1' },
  { label: 'US West (Oregon) us-west-2', value: 'us-west-2' },
  { label: 'Europe (Frankfurt) eu-central-1', value: 'eu-central-1' },
  { label: 'Europe (Ireland) eu-west-1', value: 'eu-west-1' },
]

export const TELEGRAM_DESTINATION_TYPE_OPTIONS: FieldOption[] = [
  { label: 'Chat', value: 'chat' },
  { label: 'Channel', value: 'channel' },
  { label: 'Group', value: 'group' },
]

export const SYNC_SCHEDULE_OPTIONS: FieldOption[] = [
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every 6 hours', value: '0 */6 * * *' },
  { label: 'Every 12 hours', value: '0 */12 * * *' },
  { label: 'Daily at midnight', value: '0 0 * * *' },
  { label: 'Daily at 06:00', value: '0 6 * * *' },
  { label: 'Weekly (Sunday midnight)', value: '0 0 * * 0' },
  { label: 'Manual only', value: 'manual' },
]
