export interface AppRolePermissionRow {
  id: string
  documentType: string
  onlyIfCreator?: boolean
  level?: number
  actions: string[]
}
