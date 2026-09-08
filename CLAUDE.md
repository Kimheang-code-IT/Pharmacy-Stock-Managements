# Stock & POS Management System Claude instructions

Read and follow `AGENTS.md` as the canonical repository instruction file.

Use `docs/stock_pos_ai_agent_project_spec.md` as the single source of truth for the product. Use `docs/PAGE_ROUTE_MAP.md` for the exact allowed pages/routes, `docs/IMPLEMENTATION_PLAN.md` for the legacy-to-Stock-&-POS replacement sequence, and `docs/DOCKER_INFRASTRUCTURE.md` for MinIO, RabbitMQ, Telegram bot, and Compose services.

The existing motorcycle-rental frontend and backend are legacy migration input. Do not extend rental behavior, preserve conflicting rental contracts, or expose pages and modules outside the Stock & POS specification.

Do not duplicate or override the detailed rules from `AGENTS.md` here. This file exists only to direct Claude-compatible agents to the same canonical guidance used by other repository agents.
