
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from RAG.chains import build_answer
from RAG.retreival import get_vectorstore


# ---------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------

app = FastAPI(title="RAG API")


# ---------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------

class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str


# ---------------------------------------------------------
# Health Check API
# ---------------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }


# ---------------------------------------------------------
# Ask API
# ---------------------------------------------------------

@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):

    # Remove leading/trailing spaces
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question is required."
        )

    try:
        # -------------------------------------------------
        # 1. Connect to Qdrant
        # -------------------------------------------------

        vectorstore = get_vectorstore()

        # -------------------------------------------------
        # 2. Search Qdrant for relevant chunks
        # -------------------------------------------------

        docs = vectorstore.similarity_search(
            question,
            k=5
        )

        # -------------------------------------------------
        # 3. Send retrieved documents + question to LLM
        # -------------------------------------------------

        answer = build_answer(
            question=question,
            docs=docs
        )

        # -------------------------------------------------
        # 4. Return response
        # -------------------------------------------------

        return AskResponse(
            answer=answer
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# ---------------------------------------------------------
# Run Application
# ---------------------------------------------------------

def main():
    import uvicorn

    uvicorn.run(
        "RAG.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
