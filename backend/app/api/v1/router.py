from fastapi import APIRouter

from app.api.v1 import health
from app.modules.administration.router import router as administration_router
from app.modules.auth.router import router as auth_router
from app.modules.brands.router import router as brands_router
from app.modules.categories.router import router as categories_router
from app.modules.customers.router import router as customers_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.delivery_notes.router import router as delivery_notes_router
from app.modules.image.router import router as image_router
from app.modules.pos.router import router as pos_router
from app.modules.reports.router import router as reports_router
from app.modules.stock.router import products_router, router as stock_router
from app.modules.suppliers.router import router as suppliers_router
from app.modules.uoms.router import router as uoms_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(categories_router)
api_router.include_router(uoms_router)
api_router.include_router(brands_router)
api_router.include_router(products_router)
api_router.include_router(stock_router)
api_router.include_router(suppliers_router)
api_router.include_router(customers_router)
api_router.include_router(administration_router)
api_router.include_router(pos_router)
api_router.include_router(delivery_notes_router)
api_router.include_router(dashboard_router)
api_router.include_router(reports_router)
api_router.include_router(image_router)

# All Stock & POS module routers are registered.
