.PHONY: demo-up demo-smoke demo-down demo-reset demo-logs

COMPOSE ?= docker compose -f deploy/docker-compose.demo.yml
API ?= http://127.0.0.1:8000

demo-up:
	@mkdir -p .demo
	$(COMPOSE) up -d --build
	@echo "Waiting for API health…"
	@i=0; \
	while [ $$i -lt 90 ]; do \
	  if curl -sf "$(API)/health" >/dev/null 2>&1; then \
	    echo "DEMO_READY"; \
	    echo "UI http://localhost:8080  API $(API)  admin/demo123456"; \
	    exit 0; \
	  fi; \
	  i=$$((i+1)); sleep 2; \
	done; \
	echo "ERROR: API not healthy in time. Try: make demo-logs"; exit 1

demo-smoke:
	@mkdir -p .demo
	python scripts/demo_smoke.py --base-url $(API) | tee .demo/last-smoke.log

demo-down:
	$(COMPOSE) down

demo-reset:
	$(COMPOSE) down -v
	rm -rf .demo/ready .demo/last-smoke.log

demo-logs:
	$(COMPOSE) logs --tail=200 api mysql
