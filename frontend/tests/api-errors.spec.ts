import { describe, expect, it } from 'vitest'
import { normalizeApiError } from '../app/utils/api/errors'

describe('normalizeApiError', () => {
  it('normalizes FastAPI nested detail payloads', () => {
    const error = normalizeApiError({
      detail: {
        code: 'AUTH_REQUIRED',
        message: 'Missing bearer token',
      },
    }, 401)

    expect(error.statusCode).toBe(401)
    expect(error.code).toBe('AUTH_REQUIRED')
    expect(error.message).toBe('Missing bearer token')
    expect(error.fieldErrors).toEqual({})
  })

  it('extracts field errors from the nested payload', () => {
    const error = normalizeApiError({
      detail: {
        code: 'VALIDATION_ERROR',
        message: 'Validation failed',
        field_errors: { currentPassword: 'Incorrect password' },
      },
    }, 422)

    expect(error.code).toBe('VALIDATION_ERROR')
    expect(error.fieldErrors.currentPassword).toBe('Incorrect password')
  })

  it('normalizes ordinary FastAPI validation arrays', () => {
    const error = normalizeApiError({
      detail: [
        { loc: ['body', 'email'], msg: 'value is not a valid email address', type: 'value_error' },
        { loc: ['body', 'password'], msg: 'min length is 6', type: 'value_error' },
      ],
    }, 422)

    expect(error.statusCode).toBe(422)
    expect(error.code).toBe('VALIDATION_ERROR')
    expect(error.message).toContain('email')
    expect(error.message).toContain('password')
    expect(error.fieldErrors.email).toBe('value is not a valid email address')
    expect(error.fieldErrors.password).toBe('min length is 6')
  })

  it('handles string details', () => {
    const error = normalizeApiError({ detail: 'Not found' }, 404)
    expect(error.statusCode).toBe(404)
    expect(error.message).toBe('Not found')
  })

  it('falls back to a generic message for unknown payloads', () => {
    const error = normalizeApiError({ unexpected: true }, 500)
    expect(error.statusCode).toBe(500)
    expect(error.message).toContain('Something went wrong')
  })
})
