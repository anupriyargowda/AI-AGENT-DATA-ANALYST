from langchain_groq import ChatGroq
from modules.settings import get_required_env

_client = None

def get_openai_client():
    global _client

    if _client is None:
        _client = ChatGroq(
            groq_api_key=get_required_env("OPENAI_API_KEY"),
            model_name="llama-3.1-8b-instant"
        )

    return _client