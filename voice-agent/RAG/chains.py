from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
import os
from pathlib import Path
from dotenv import load_dotenv

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
    return chain.invoke({"context": format_docs(docs), "question": question})


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