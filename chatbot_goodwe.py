from pathlib import Path
from langchain.chat_models import init_chat_model
from langchain_openai import OpenAIEmbeddings
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_community.document_loaders import UnstructuredWordDocumentLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from typing import List, TypedDict
from langgraph.graph import START, StateGraph

llm = init_chat_model("gpt-4o-mini", model_provider="openai")

docs = []
for file_path in sorted(Path("./docs").glob("*")):
    if file_path.suffix.lower() == ".pdf":
        docs.extend(PyPDFLoader(str(file_path)).load())
    elif file_path.suffix.lower() in {".docx", ".doc"}:
        docs.extend(UnstructuredWordDocumentLoader(str(file_path)).load())

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, add_start_index=True)
splits = text_splitter.split_documents(docs)

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
vector_store = InMemoryVectorStore(embeddings)
vector_store.add_documents(splits)

class State(TypedDict):
    question: str
    context: List[Document]
    answer: str

def retrieve(state: State):
    retrieved_docs = vector_store.similarity_search(state["question"])
    return {"context": retrieved_docs}

SYSTEM_PROMPT = """
Você é o Chatbot GoodWe, um assistente operacional para o ChargeGrid Intelligence.
Sua persona é o operador comercial de eletropostos.
Seu papel é responder perguntas sobre:
- Potência utilizada
- Ciclos de carregamento
- Faturamento
- Comunicação com usuários
- Gestão de horários de pico
Responda sempre de forma clara, objetiva e contextualizada ao EV Challenge 2026.
"""

def generate(state: State):
    docs_content = "\n\n".join(doc.page_content for doc in state["context"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Pergunta: {state['question']}\n\nContexto:\n{docs_content}"}
    ]
    response = llm.invoke(messages)
    return {"answer": response.content}

graph_builder = StateGraph(State).add_sequence([retrieve, generate])
graph_builder.add_edge(START, "retrieve")
graph = graph_builder.compile()

if __name__ == "__main__":
    pergunta = "Qual foi meu pico de potência ontem?"
    result = graph.invoke({"question": pergunta})
    print(f"Answer: {result['answer']}\n")
    print("Docs usados:")
    for doc in result["context"]:
        source = doc.metadata.get("source", "desconhecido")
        page = doc.metadata.get("page", "sem página")
        print(f"- {source} | página {page}")