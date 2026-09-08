import { describe, expect, it } from 'vitest'
import { headerListNavDisabled } from '../app/utils/layout/header-actions'

describe('header list nav', () => {
  it('disables previous/next on create, list ends, and while a nav request is in flight', () => {
    expect(headerListNavDisabled({
      isCreate: false,
      canNavigate: true,
      loading: false,
      direction: null,
    })).toBe(false)

    expect(headerListNavDisabled({
      isCreate: true,
      canNavigate: true,
      loading: false,
      direction: null,
    })).toBe(true)

    expect(headerListNavDisabled({
      isCreate: false,
      canNavigate: false,
      loading: false,
      direction: null,
    })).toBe(true)

    expect(headerListNavDisabled({
      isCreate: false,
      canNavigate: true,
      loading: true,
      direction: null,
    })).toBe(true)

    expect(headerListNavDisabled({
      isCreate: false,
      canNavigate: true,
      loading: false,
      direction: 'next',
    })).toBe(true)
  })
})
