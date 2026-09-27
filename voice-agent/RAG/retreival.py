import os

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_qdrant import QdrantVectorStore


load_dotenv()


COLLECTION_NAME = "chunks for voice agent"


def _get_embeddings():
    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )


def get_vectorstore():
    """
    Connect to the existing Qdrant collection.
    """

    qdrant_url = os.getenv("QDRANT_URL")

    if not qdrant_url:
        raise ValueError("QDRANT_URL not found in environment variables")

    client = QdrantClient(url=qdrant_url)

    # Check whether collection exists
    try:
        client.get_collection(
            collection_name=COLLECTION_NAME
        )
    except Exception as e:
        raise RuntimeError(
            f"Qdrant collection '{COLLECTION_NAME}' "
            f"does not exist. Error: {e}"
        )

    return QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding=_get_embeddings(),
        content_payload_key="page_content",
    )


def get_retrieval():
    """
    Return a retriever that searches chunks stored in Qdrant.
    """

    vectorstore = get_vectorstore()

    retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={
            "k": 5
        },
    )

    return retriever