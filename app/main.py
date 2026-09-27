from fastapi import FastAPI

app = FastAPI(title="Vet Clinic CRM")


@app.get("/")
async def root():
    return {"message": "Vet CRM API is running"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
