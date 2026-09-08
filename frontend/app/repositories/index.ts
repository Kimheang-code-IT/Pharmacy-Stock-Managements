import type { AppConfigRepository, AppInfoRepository, StorageRepository } from '~/repositories/contracts/settings'
import type {
  DeliveryCommandRepository,
  EntityRepository,
  FinanceRepository,
  PosCommandRepository,
  SearchRepository,
  StockQueryRepository,
} from '~/repositories/contracts/entities'
import { createHttpAppConfigRepository, createHttpAppInfoRepository } from '~/repositories/http/settings'
import { createHttpStorageRepository } from '~/repositories/http/settings-storage'
import { createHttpDeliveryRepository } from '~/repositories/http/delivery'
import {
  createHttpEntityRepository,
  createHttpFinanceRepository,
  createHttpPosCommandRepository,
  createHttpSearchRepository,
  createHttpStockQueryRepository,
} from '~/repositories/http/entities'
import { createMockAppConfigRepository, createMockAppInfoRepository, createMockStorageRepository } from '~/repositories/mock/settings'
import { createMockDeliveryRepository } from '~/repositories/mock/delivery'
import {
  createMockEntityRepository,
  createMockFinanceRepository,
  createMockPosRepository,
  createMockSearchRepository,
  createMockStockQueryRepository,
} from '~/repositories/mock/entities'

let appInfoRepo: AppInfoRepository
let appConfigRepo: AppConfigRepository
let storageRepo: StorageRepository
let entityRepo: EntityRepository
let stockQueryRepo: StockQueryRepository
let posCommandRepo: PosCommandRepository
let deliveryCommandRepo: DeliveryCommandRepository
let financeRepo: FinanceRepository
let searchRepo: SearchRepository
let initialized = false

function useMockMode(): boolean {
  try {
    return useRuntimeConfig().public.useMockData === true
  }
  catch {
    return false
  }
}

function ensureRepositories() {
  if (initialized) return
  initialized = true
  if (useMockMode()) {
    appInfoRepo = createMockAppInfoRepository()
    appConfigRepo = createMockAppConfigRepository()
    storageRepo = createMockStorageRepository()
    entityRepo = createMockEntityRepository()
    stockQueryRepo = createMockStockQueryRepository()
    posCommandRepo = createMockPosRepository()
    deliveryCommandRepo = createMockDeliveryRepository()
    financeRepo = createMockFinanceRepository()
    searchRepo = createMockSearchRepository()
    return
  }
  appInfoRepo = createHttpAppInfoRepository()
  appConfigRepo = createHttpAppConfigRepository()
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