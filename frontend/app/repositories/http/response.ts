import type { ApiResponse } from '~/types/stock-pos/common'

export function unwrapApiData<T>(response: T | ApiResponse<T>): T {
  if (
    response
    && typeof response === 'object'
    && 'data' in response
  ) {
    return (response as ApiResponse<T>).data
  }
  return response as T
}
