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
    chat_history: List[dict]

def retrieve(state: State):
    retrieved_docs = vector_store.similarity_search(state["question"], k=2)
    return {"context": retrieved_docs}

SYSTEM_PROMPT = """
Você é o Chatbot GoodWe, assistente operacional do ChargeGrid Intelligence no contexto do EV Challenge 2026.

Regras:
- Responda sempre em português do Brasil.
- Seja extremamente objetivo.
- Utilize no máximo 2 frases curtas.
- Não use listas.
- Utilize o histórico da conversa para compreender referências como "esse valor", "isso" e "o resultado anterior".
- Perguntas sobre sua função ou capacidades podem ser respondidas usando sua descrição institucional.
- Quando houver um dado exato no contexto recuperado, informe apenas o dado relevante.
- Nunca invente valores ou registros que não estejam presentes no contexto.
- Quando não houver dados suficientes, informe que o valor exato não foi encontrado e oriente brevemente como obtê-lo.
- Não ofereça ajuda adicional ao final da resposta.

Você auxilia operadores comerciais com dúvidas sobre potência, faturamento, ciclos de carregamento, comunicação com usuários e gestão de horários de pico.
"""

def generate(state: State):
    docs_content = "\n\n".join(
        doc.page_content for doc in state["context"]
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    messages.extend(state.get("chat_history", []))
    messages.append({
    "role": "user",
    "content": (
        f"""
        Pergunta do usuário: {state['question']}
        Contexto recuperado: {docs_content if docs_content else "Nenhum contexto recuperado."}
        
        Utilize o contexto recuperado quando a pergunta exigir dados, registros ou informações presentes nos documentos
        Perguntas sobre sua identidade, função, objetivo ou capacidades podem ser respondidas usando sua descrição institucional.
        """
        )
        })

    response = llm.invoke(messages)

    updated_history = state.get("chat_history", []).copy()

    updated_history.append({
        "role": "user",
        "content": state["question"]
    })

    updated_history.append({
        "role": "assistant",
        "content": response.content
    })

    return {
        "answer": response.content,
        "chat_history": updated_history
    }

graph_builder = StateGraph(State).add_sequence([retrieve, generate])
graph_builder.add_edge(START, "retrieve")
graph = graph_builder.compile()

if __name__ == "__main__":
    chat_history = []

    while True:
        pergunta = input("\nVocê: ")

        if pergunta.lower() in ["sair", "exit", "quit"]:
            break

        result = graph.invoke({
            "question": pergunta,
            "chat_history": chat_history
        })

        print(f"\nChatbot: {result['answer']}")

        chat_history = result["chat_history"]

        print("\nDocs usados:")
        for doc in result["context"]:
            source = doc.metadata.get("source", "desconhecido")
            page = doc.metadata.get("page", "sem página")
            print(f"- {source} | página {page}")