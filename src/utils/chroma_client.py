import chromadb
from chromadb.utils import embedding_functions
from src.config import CHROMA_DB_DIR, EMBEDDING_MODEL

def get_chroma_collection(name: str = "prisoners_of_geography"):
    client = chromadb.Client(chromadb.config.Settings(persist_directory=CHROMA_DB_DIR))
    try:
        collection = client.get_collection(name=name)
    except Exception:
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        collection = client.create_collection(name=name, embedding_function=ef)
    return collection
