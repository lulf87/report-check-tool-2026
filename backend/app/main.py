from fastapi import FastAPI

from app.routers.report_self_check import router as report_self_check_router


app = FastAPI(title="Report Self Check Codex Judge")
app.include_router(report_self_check_router, prefix="/api/report-self-check", tags=["report-self-check"])
