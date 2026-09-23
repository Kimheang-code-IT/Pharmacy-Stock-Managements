import { describe, expect, it } from 'vitest'
import { effectScope } from 'vue'
import {
  clearPublishedFieldErrors,
  fieldErrorFor,
  fieldErrorsFromError,
  hasActiveFieldErrorSink,
  hasUnclaimedFieldError,
  publishFieldErrors,
  useFormErrors,
} from '../app/composables/useFormErrors'

describe('form field errors', () => {
  it('publishes and clears field errors', () => {
    publishFieldErrors({ customer_id: 'Select a registered customer' })
    expect(fieldErrorFor('customer_id')).toBe('Select a registered customer')
    clearPublishedFieldErrors()
    expect(fieldErrorFor('customer_id')).toBeUndefined()
  })

  it('resolves camelCase field keys against snake_case backend keys', () => {
    publishFieldErrors({ customer_id: 'Select a customer', paid_amount: 'Full payment required' })
    expect(fieldErrorFor('customerId')).toBe('Select a customer')
    expect(fieldErrorFor('paidAmount')).toBe('Full payment required')
    clearPublishedFieldErrors()
  })

  it('resolves snake_case field keys against camelCase backend keys', () => {
    publishFieldErrors({ currentPassword: 'Incorrect password' })
    expect(fieldErrorFor('current_password')).toBe('Incorrect password')
    clearPublishedFieldErrors()
  })

  it('reads field errors off an API error payload', () => {
    const errors = fieldErrorsFromError({
      statusCode: 422,
      data: { detail: { code: 'VALIDATION_ERROR', message: 'x', field_errors: { name: 'Required' } } },
    })
    expect(errors).toEqual({ name: 'Required' })
  })

  it('claims keys while a form scope is alive', () => {
    const scope = effectScope()
    scope.run(() => {
      const form = useFormErrors()
      form.claim('customerId')
      expect(hasActiveFieldErrorSink()).toBe(true)
      expect(hasUnclaimedFieldError({ customer_id: 'x' })).toBe(false)
    })
    // Releasing the scope drops the claim, so an unmapped error must toast.
    scope.stop()
    expect(hasActiveFieldErrorSink()).toBe(false)
    expect(hasUnclaimedFieldError({ customer_id: 'x' })).toBe(true)
  })

  it('flags errors that no mounted field can render', () => {
    const scope = effectScope()
    scope.run(() => {
      useFormErrors().claim('name')
      expect(hasUnclaimedFieldError({ name: 'Required' })).toBe(false)
      expect(hasUnclaimedFieldError({ name: 'Required', permissions: 'Invalid' })).toBe(true)
    })
    scope.stop()
  })
})
