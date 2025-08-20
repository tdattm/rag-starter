# Import các thư viện cần thiết
from langchain.tools.retriever import create_retriever_tool  # Tạo công cụ tìm kiếm
from langchain_openai import ChatOpenAI  # Model ngôn ngữ OpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent  # Tạo và thực thi agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder  # Xử lý prompt
from seed_data import seed_milvus, connect_to_milvus  # Kết nối với Milvus
from langchain_community.callbacks.streamlit import StreamlitCallbackHandler  # Xử lý callback cho Streamlit
from langchain_community.chat_message_histories import StreamlitChatMessageHistory  # Lưu trữ lịch sử chat
from langchain.retrievers import EnsembleRetriever  # Kết hợp nhiều retriever
from langchain_community.retrievers import BM25Retriever  # Retriever dựa trên BM25
from langchain_core.documents import Document  # Lớp Document
import google.generativeai as genai  # Thêm import Gemini
from langchain_core.language_models import BaseLanguageModel  # Import base class
from langchain_core.runnables import Runnable # Import Runnable để sử dụng trong Gemini
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import os

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY not found in environment variables")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment variables")

XAI_API_KEY = os.getenv("XAI_API_KEY")
if not XAI_API_KEY:
    raise ValueError("XAI_API_KEY not found in environment variables")

def get_retriever(collection_name: str = "data_test") -> EnsembleRetriever:
    """
    Tạo một ensemble retriever kết hợp vector search (Milvus) và BM25
    Args:
        collection_name (str): Tên collection trong Milvus để truy vấn
    """
    try:
        # Kết nối với Milvus và tạo vector retriever
        vectorstore = connect_to_milvus('http://localhost:19530', collection_name)
        milvus_retriever = vectorstore.as_retriever(
            search_type="similarity", 
            search_kwargs={"k": 4}
        )

        # Tạo BM25 retriever từ toàn bộ documents
        documents = [
            Document(page_content=doc.page_content, metadata=doc.metadata)
            for doc in vectorstore.similarity_search("", k=100)
        ]
        
        if not documents:
            raise ValueError(f"Không tìm thấy documents trong collection '{collection_name}'")
            
        bm25_retriever = BM25Retriever.from_documents(documents)
        bm25_retriever.k = 4

        # Kết hợp hai retriever với tỷ trọng
        ensemble_retriever = EnsembleRetriever(
            retrievers=[milvus_retriever, bm25_retriever],
            weights=[0.7, 0.3]
        )
        return ensemble_retriever
        
    except Exception as e:
        print(f"Lỗi khi khởi tạo retriever: {str(e)}")
        # Trả về retriever với document mặc định nếu có lỗi
        default_doc = [
            Document(
                page_content="Có lỗi xảy ra khi kết nối database. Vui lòng thử lại sau.",
                metadata={"source": "error"}
            )
        ]
        return BM25Retriever.from_documents(default_doc)

class GeminiLLM(Runnable):
    def __init__(self, api_key, model_name="gemini-1.5-flash", temperature=0):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.temperature = temperature

    def invoke(self, input, **kwargs):
        response = self.model.generate_content(input)
        return response.text

def get_llm_and_agent(_retriever, model_choice="gemini") -> AgentExecutor:
    """
    Khởi tạo Language Model và Agent với cấu hình cụ thể
    Args:
        _retriever: Retriever đã được cấu hình để tìm kiếm thông tin
        model_choice: Lựa chọn model ("gpt4", "gemini" hoặc "grok")
    """
    # Khởi tạo ChatOpenAI dựa trên lựa chọn model
    if model_choice == "gpt4":
        llm = ChatOpenAI(
            temperature=0,
            streaming=True,
            model='gpt-4',
            api_key=OPENAI_API_KEY)
    elif model_choice == "gemini":
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=GEMINI_API_KEY,
            temperature=0
        )
    else:  # grok
        llm = ChatOpenAI(
            temperature=0, 
            streaming=True, 
            model='grok-beta', 
            api_key=XAI_API_KEY, 
            base_url='https://api.x.ai/v1')
    
    # Tạo công cụ tìm kiếm cho agent
    tool = create_retriever_tool(
        _retriever,
        "find_documents",
        "Search for information of Stack AI."
    )
    
    tools = [tool]
    
    # Thiết lập prompt template cho agent
    system = """
    You are an expert AI assistant named "MIM chatbot".
    Your main task is to answer user questions by searching for information using the 'find_documents' tool.
    For every user question, ALWAYS call the 'find_documents' tool first before answering.
    Do NOT answer directly without using the tool, regardless of the language (English, Vietnamese, etc.).
    If the tool does not return relevant information, you may say you cannot find an answer.
    Important: Always respond in Vietnamese

    For example:
    - If the user asks in English: "What is Stack AI?" → Call 'find_documents'.
    - If the user asks in Vietnamese: "Stack AI là gì?" → Also call 'find_documents'.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # Tạo và trả về agent
    agent = create_openai_functions_agent(llm=llm, tools=tools, prompt=prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=True)

# Khởi tạo retriever và agent
retriever = get_retriever()
agent_executor = get_llm_and_agent(retriever)