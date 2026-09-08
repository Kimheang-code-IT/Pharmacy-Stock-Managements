import { getByPath, setByPath } from '~/utils/object-path'

type ModelRef<T extends object> = { value: T | null | undefined }

/** Shared field access for schema-driven forms backed by nested object paths. */
export function usePathModel<T extends object>(model: ModelRef<T>) {
  function fieldValue(key: string): unknown {
    return model.value ? getByPath(model.value, key) : undefined
  }

  function setFieldValue(key: string, value: unknown): void {
    if (model.value) setByPath(model.value as Record<string, unknown>, key, value)
  }

  return { fieldValue, setFieldValue }
}
