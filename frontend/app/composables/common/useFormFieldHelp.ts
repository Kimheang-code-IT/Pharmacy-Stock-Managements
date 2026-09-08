import { resolveFormFieldHelp, type FormFieldHelpSource } from '~/utils/field-help'

/** ERPNext-style helper text for any form field (schema or one-off UFormField). */
export function useFormFieldHelp() {
  const { t, te } = useI18n()

  function fieldHelp(field: FormFieldHelpSource) {
    return resolveFormFieldHelp(field, t, te)
  }

  return { fieldHelp }
}
