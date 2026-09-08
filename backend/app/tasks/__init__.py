"""Approved Celery infrastructure for Stock & POS async jobs.

Task modules are added per vertical slice (telegram delivery, invoices,
exports, maintenance). Queues mirror the Compose worker services.
"""
