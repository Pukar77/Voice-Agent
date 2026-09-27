import os
from pathlib import Path
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()


# ============================================================
# Configuration
# ============================================================

TXT_FILE = "Apex_Global_Technologies_Enterprise_Knowledge_Base.txt"
COLLECTION_NAME = "chunks for voice agent"

QDRANT_URL = os.getenv("QDRANT_URL")

if(not QDRANT_URL):
    print("Qdrant url not found in the env file")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200




# ============================================================
# Load TXT file
# ============================================================

def load_text_file(file_path: str) -> str:
    """
    Read the complete knowledge-base TXT file.
    """

    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Knowledge base file not found: {path.resolve()}"
        )

    with open(path, "r", encoding="utf-8") as file:
        text = file.read()

    if not text.strip():
        raise ValueError(
            f"Knowledge base file is empty: {path.resolve()}"
        )

    return text


# ============================================================
# Fixed-size chunking with overlap
# ============================================================

def create_chunks(text: str):
    """
    Split the knowledge base into fixed-size chunks
    with overlapping content.
    """

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
            ""
        ],
    )

    chunks = text_splitter.split_text(text)

    print(f"📄 Total characters: {len(text)}")
    print(f"🧩 Total chunks created: {len(chunks)}")
    print(f"📏 Chunk size: {CHUNK_SIZE}")
    print(f"🔁 Chunk overlap: {CHUNK_OVERLAP}")

    return chunks


# ============================================================
# Create embeddings
# ============================================================

def get_embeddings():
    """
    Load the HuggingFace embedding model.
    """

    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )


# ============================================================
# Create Qdrant vector store
# ============================================================

def vector_store(chunks):
    """
    Create Qdrant collection and insert chunks.
    """

    embeddings = get_embeddings()

    print(f"🔗 Connecting to Qdrant: {QDRANT_URL}")

    vectorstore = QdrantVectorStore.from_texts(
        texts=chunks,
        embedding=embeddings,
        url=QDRANT_URL,
        collection_name=COLLECTION_NAME,
        force_recreate=True,
    )

    client = QdrantClient(url=QDRANT_URL)

    count = client.count(
        collection_name=COLLECTION_NAME
    )

    print(
        f"📦 Total vectors inserted: {count.count}"
    )

    return vectorstore


# ============================================================
# Main ingestion function
# ============================================================

def ingest_knowledge_base():
    """
    Complete TXT → chunks → embeddings → Qdrant pipeline.
    """

    print("🚀 Starting knowledge-base ingestion...")

    # 1. Read TXT file
    text = load_text_file(TXT_FILE)

    # 2. Create fixed-size overlapping chunks
    chunks = create_chunks(text)

    if not chunks:
        raise ValueError(
            "No chunks were created from the knowledge base."
        )

    # 3. Generate embeddings and store in Qdrant
    vectorstore = vector_store(chunks)

    print("✅ Knowledge base successfully stored in Qdrant.")

    return vectorstore


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    ingest_knowledge_base()