from fastapi import FastAPI

app = FastAPI()  # <- nazwa obiektu 'app' musi pasować do polecenia startowego

@app.get("/")
def read_root():
    return {"message": "Hello World!"}