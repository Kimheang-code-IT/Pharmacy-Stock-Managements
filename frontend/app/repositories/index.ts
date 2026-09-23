import type { AppConfigRepository, AppInfoRepository, BackupRepository, StorageRepository } from '~/repositories/contracts/settings'
import type {
  DeliveryCommandRepository,
  EntityRepository,
  FinanceRepository,
  PosCommandRepository,
  SearchRepository,
  StockQueryRepository,
} from '~/repositories/contracts/entities'
import { createHttpAppConfigRepository, createHttpAppInfoRepository } from '~/repositories/http/settings'
import { createHttpBackupRepository } from '~/repositories/http/backup'
import { createHttpStorageRepository } from '~/repositories/http/settings-storage'
import { createHttpDeliveryRepository } from '~/repositories/http/delivery'
import {
  createHttpEntityRepository,
  createHttpFinanceRepository,
  createHttpPosCommandRepository,
  createHttpSearchRepository,
  createHttpStockQueryRepository,
} from '~/repositories/http/entities'

let appInfoRepo: AppInfoRepository
let appConfigRepo: AppConfigRepository
let backupRepo: BackupRepository
let storageRepo: StorageRepository
let entityRepo: EntityRepository
let stockQueryRepo: StockQueryRepository
let posCommandRepo: PosCommandRepository
let deliveryCommandRepo: DeliveryCommandRepository
let financeRepo: FinanceRepository
let searchRepo: SearchRepository
let initialized = false

function ensureRepositories() {
  if (initialized) return
  initialized = true
  appInfoRepo = createHttpAppInfoRepository()
  appConfigRepo = createHttpAppConfigRepository()
  backupRepo = createHttpBackupRepository()
  storageRepo = createHttpStorageRepository()
  entityRepo = createHttpEntityRepository()
  stockQueryRepo = createHttpStockQueryRepository()
  posCommandRepo = createHttpPosCommandRepository()
  deliveryCommandRepo = createHttpDeliveryRepository()
  financeRepo = createHttpFinanceRepository()
  searchRepo = createHttpSearchRepository()
}

export function useSettingsRepositories() {
  ensureRepositories()
  return { appInfo: appInfoRepo!, appConfig: appConfigRepo!, storage: storageRepo! }
}

export function useBackupRepository(): BackupRepository {
  ensureRepositories()
  return backupRepo!
}

export function useEntityRepository(): EntityRepository {
  ensureRepositories()
  return entityRepo!
}

/** Product-scoped dialog queries (history / cost-history / sale prices). */
export function useStockQueries(): StockQueryRepository {
  ensureRepositories()
  return stockQueryRepo!
}

export function usePosCommands(): PosCommandRepository {
  ensureRepositories()
  return posCommandRepo!
}

export function useDeliveryCommands(): DeliveryCommandRepository {
  ensureRepositories()
  return deliveryCommandRepo!
}

export function useFinanceRepository(): FinanceRepository {
  ensureRepositories()
  return financeRepo!
}

export function useSearchRepository(): SearchRepository {
  ensureRepositories()
  return searchRepo!
}