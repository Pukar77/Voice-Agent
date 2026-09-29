from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
import os
import re
from pathlib import Path
from dotenv import load_dotenv

from RAG.retreival import TOP_K, get_vectorstore

_ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=_ENV_PATH)

def get_llm():
    llm = ChatGroq(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        api_key=os.getenv("GROQ_API_KEY"),
        temperature=0.2
    )
    return llm


def format_docs(docs):
    return "\n\n".join([doc.page_content for doc in docs])


# The model answers in markdown ("The CEO is **Jane Doe**."). Those markers
# show up literally in the transcript pane, and edge-tts reads the asterisks
# out loud, so they are removed where the answer is built: terminal, browser
# and voice all get the same plain sentence.
#
# Single underscores are deliberately left alone: they are far more likely to
# be part of a word (snake_case) than emphasis.
_MD_MARKERS = re.compile(r"\*\*|__|\*|`+|~~")


def strip_markdown(text):
    """Drop the emphasis markers, keep the words and the line breaks."""
    return _MD_MARKERS.sub("", text or "")


_PROMPT = ChatPromptTemplate.from_template("""
You are a helpful assistant.
Use the following retrieved context to answer the user's question accurately.
If the answer is not in the context, say "I don't have enough information to answer that."

Context:
{context}

Question:
{question}

Answer:
""")


def build_answer(question, docs):
    llm = get_llm()
    chain = _PROMPT | llm | StrOutputParser()
    answer = chain.invoke({"context": format_docs(docs), "question": question})
    return strip_markdown(answer)


def get_rag_chain(retriever):

    llm = get_llm()

    rag_chain = (
        {
            "context": retriever | format_docs,
            "question": RunnablePassthrough()
        }
        | _PROMPT
        | llm
        | StrOutputParser()
    )

    return rag_chain


def ask(question, k=TOP_K):
    """
    Answer a question from the Qdrant knowledge base.

    This is the single call the voice agent needs: retrieve the relevant
    chunks, then let the LLM answer from them.
    """
    question = (question or "").strip()

    if not question:
        raise ValueError("Question is required.")

    docs = get_vectorstore().similarity_search(question, k=k)

    return build_answer(
        question=question,
        docs=docs
    )


def preload():
    """
    Load the embedding model and confirm Qdrant is reachable.

    Worth calling at startup: it moves the multi-second model load out of the
    user's first question.
    """
    vectorstore = get_vectorstore()

    vectorstore.similarity_search("warm up the embedding model", k=1)

    print("Knowledge base ready.")
